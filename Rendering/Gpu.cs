using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Vortice.D3DCompiler;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;

namespace ClockWall.Rendering;

/// <summary>
/// Small helpers over Vortice that the scene would otherwise repeat: shader
/// compilation from the embedded HLSL, constant-buffer upload, and the
/// vertex layout every mesh in the watch shares.
///
/// Shaders compile from source at start-up through the system
/// d3dcompiler_47.dll. That costs a few hundred milliseconds once, and it
/// buys the absence of an offline shader build - there is no fxc step,
/// nothing to forget to re-run, and nothing unsigned on disk for Smart App
/// Control to object to (see CLAUDE.md).
/// </summary>
internal static class Gpu
{
    /// <summary>Position and normal, twelve floats of nothing else. Every mesh
    /// the watch draws - the CAD movement, the lathed case, the hands - is
    /// this, which is what lets one input layout serve all of them.</summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct Vertex
    {
        public System.Numerics.Vector3 Position;
        public System.Numerics.Vector3 Normal;
        public const int Stride = 24;
    }

    public static readonly InputElementDescription[] VertexLayout =
    {
        new("POSITION", 0, Format.R32G32B32_Float, 0, 0),
        new("NORMAL", 0, Format.R32G32B32_Float, 12, 0),
    };

    public static string LoadShaderSource(string name)
    {
        var asm = Assembly.GetExecutingAssembly();
        using var stream = asm.GetManifestResourceStream($"ClockWall.Rendering.Shaders.{name}")
            ?? throw new FileNotFoundException($"embedded shader {name} missing");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    public static Blob Compile(string file, string entry, string profile)
    {
        var source = LoadShaderSource(file);
        var result = Compiler.Compile(source, entry, file, profile, out var blob, out var errors);
        if (result.Failure || blob is null)
        {
            var message = errors is not null ? errors.AsString() : result.ToString();
            errors?.Dispose();
            throw new InvalidOperationException($"{file}:{entry} failed to compile:\n{message}");
        }

        errors?.Dispose();
        return blob;
    }

    /// <summary>
    /// A single-channel texture from a PNG, through the WinRT decoder the
    /// screenshot path already uses. The one image the face loads is the
    /// dial's printing (see tools/dial_print.py); everything else it shows
    /// is geometry and light.
    /// </summary>
    /// <summary>A colour PNG as an RGBA8 texture, channels kept: the
    /// crystal's wear mask carries three (scratch, dust, direction).</summary>
    public static ID3D11ShaderResourceView LoadRgba(ID3D11Device device, string path)
    {
        using var stream = File.OpenRead(path);
        var decoder = Windows.Graphics.Imaging.BitmapDecoder.CreateAsync(stream.AsRandomAccessStream()).AsTask().GetAwaiter().GetResult();
        var bgra = decoder.GetPixelDataAsync(
            Windows.Graphics.Imaging.BitmapPixelFormat.Bgra8,
            Windows.Graphics.Imaging.BitmapAlphaMode.Ignore,
            new Windows.Graphics.Imaging.BitmapTransform(),
            Windows.Graphics.Imaging.ExifOrientationMode.IgnoreExifOrientation,
            Windows.Graphics.Imaging.ColorManagementMode.DoNotColorManage).AsTask().GetAwaiter().GetResult().DetachPixelData();
        var width = (int)decoder.PixelWidth;
        var height = (int)decoder.PixelHeight;
        var description = new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.B8G8R8A8_UNorm, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Immutable, BindFlags = BindFlags.ShaderResource,
        };
        unsafe
        {
            fixed (byte* p = bgra)
            {
                using var texture = device.CreateTexture2D(description, new[] { new SubresourceData((nint)p, (uint)(width * 4)) });
                return device.CreateShaderResourceView(texture);
            }
        }
    }

    public static ID3D11ShaderResourceView LoadMask(ID3D11Device device, string path)
    {
        using var stream = File.OpenRead(path);
        var decoder = Windows.Graphics.Imaging.BitmapDecoder.CreateAsync(stream.AsRandomAccessStream()).AsTask().GetAwaiter().GetResult();
        // BGRA8 rather than Gray8: the decoder refuses Gray8 for this PNG
        // ("one or more parameters are invalid"), and BGRA8 is the one
        // format every WIC codec can hand back. One channel is kept.
        var bgra = decoder.GetPixelDataAsync(
            Windows.Graphics.Imaging.BitmapPixelFormat.Bgra8,
            Windows.Graphics.Imaging.BitmapAlphaMode.Ignore,
            new Windows.Graphics.Imaging.BitmapTransform(),
            Windows.Graphics.Imaging.ExifOrientationMode.IgnoreExifOrientation,
            Windows.Graphics.Imaging.ColorManagementMode.DoNotColorManage).AsTask().GetAwaiter().GetResult().DetachPixelData();

        var width = (int)decoder.PixelWidth;
        var height = (int)decoder.PixelHeight;
        var pixels = new byte[width * height];
        for (var k = 0; k < pixels.Length; k++) pixels[k] = bgra[k * 4];
        var description = new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.R8_UNorm, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Immutable, BindFlags = BindFlags.ShaderResource,
        };
        unsafe
        {
            fixed (byte* p = pixels)
            {
                using var texture = device.CreateTexture2D(description, new[] { new SubresourceData((nint)p, (uint)width) });
                return device.CreateShaderResourceView(texture);
            }
        }
    }

    public static ID3D11Buffer CreateConstantBuffer<T>(ID3D11Device device) where T : unmanaged
    {
        // Constant buffers must be a multiple of 16 bytes; the structs are
        // padded to that by hand, and this is the check that they were.
        var size = Unsafe.SizeOf<T>();
        if (size % 16 != 0)
        {
            throw new InvalidOperationException($"{typeof(T).Name} is {size} bytes; constant buffers pad to 16");
        }

        return device.CreateBuffer(new BufferDescription((uint)size, BindFlags.ConstantBuffer, ResourceUsage.Default));
    }

    public static ID3D11Buffer CreateVertexBuffer(ID3D11Device device, ReadOnlySpan<Vertex> vertices)
    {
        return device.CreateBuffer(vertices, new BufferDescription((uint)(vertices.Length * Vertex.Stride), BindFlags.VertexBuffer));
    }

    public static ID3D11Buffer CreateIndexBuffer(ID3D11Device device, ReadOnlySpan<uint> indices)
    {
        return device.CreateBuffer(indices, new BufferDescription((uint)(indices.Length * 4), BindFlags.IndexBuffer));
    }
}
