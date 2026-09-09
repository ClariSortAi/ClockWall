using System;
using System.Diagnostics;
using System.IO;
using System.Numerics;
using System.Runtime.InteropServices;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Vortice.Mathematics;

namespace ClockWall.Rendering;

/// <summary>
/// The lighting environment: the studio HDRI the offline render uses,
/// turned once at load into the three lookups a real-time PBR shader wants -
/// a GGX-prefiltered specular cube with one mip per roughness, a
/// cosine-convolved diffuse cube, and the split-sum BRDF table.
///
/// tools/hdri/SOURCE.txt makes the argument for why a measured studio IS the
/// material for an all-metal watch: a metal shows nothing but what it
/// reflects, so the softboxes in that panorama are the highlights on the
/// case, and their size and softness is what makes steel read as steel.
/// Everything here is done once and then only sampled.
/// </summary>
internal sealed class Environment : IDisposable
{
    public const int SpecularSize = 256;
    public const int SpecularMips = 6;
    public const int DiffuseSize = 32;
    public const int LutSize = 256;

    public ID3D11ShaderResourceView Specular { get; }
    public ID3D11ShaderResourceView Diffuse { get; }
    public ID3D11ShaderResourceView BrdfLut { get; }

    /// <summary>The irradiance the baked environment delivers to a surface
    /// whose normal points along <c>dialNormalInEnv</c>, in the HDRI's own
    /// units (pi times the irradiance map's value there). This is what
    /// calibrates the room: "ambient N lux" scales the HDRI so this reads N.
    /// Read back off the diffuse cube after the bake, from the texel that
    /// direction lands on.</summary>
    public float IrradianceUnits { get; private set; }

    private readonly ID3D11Texture2D _specularTex;
    private readonly ID3D11Texture2D _diffuseTex;
    private readonly ID3D11Texture2D _lutTex;

    [StructLayout(LayoutKind.Sequential)]
    private struct Params
    {
        public int Face;
        public float Roughness;
        public float SourceSize;
        public int Samples;
    }

    private static float ReadIrradiance(ID3D11Device device, ID3D11DeviceContext context, ID3D11Texture2D cube, Vector3 dir)
    {
        // The cube face and texel the direction lands on, D3D's convention.
        var a = new[] { MathF.Abs(dir.X), MathF.Abs(dir.Y), MathF.Abs(dir.Z) };
        int face; float u, v, m;
        if (a[0] >= a[1] && a[0] >= a[2]) { m = a[0]; face = dir.X > 0 ? 0 : 1; u = dir.X > 0 ? -dir.Z : dir.Z; v = -dir.Y; }
        else if (a[1] >= a[2]) { m = a[1]; face = dir.Y > 0 ? 2 : 3; u = dir.X; v = dir.Y > 0 ? dir.Z : -dir.Z; }
        else { m = a[2]; face = dir.Z > 0 ? 4 : 5; u = dir.Z > 0 ? dir.X : -dir.X; v = -dir.Y; }
        var px = (int)Math.Clamp((u / m * 0.5f + 0.5f) * DiffuseSize, 0, DiffuseSize - 1);
        var py = (int)Math.Clamp((v / m * 0.5f + 0.5f) * DiffuseSize, 0, DiffuseSize - 1);

        using var staging = device.CreateTexture2D(new Texture2DDescription
        {
            Width = DiffuseSize, Height = DiffuseSize, MipLevels = 1, ArraySize = 1,
            Format = Format.R16G16B16A16_Float, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Staging, CPUAccessFlags = CpuAccessFlags.Read,
        });
        context.CopySubresourceRegion(staging, 0, 0, 0, 0, cube, (uint)face);
        var map = context.Map(staging, 0, MapMode.Read);
        try
        {
            // A 3x3 mean round the texel: the map is smooth, and it dodges a
            // face seam.
            float sum = 0; var n = 0;
            for (var dy = -1; dy <= 1; dy++)
            for (var dx = -1; dx <= 1; dx++)
            {
                var x = Math.Clamp(px + dx, 0, DiffuseSize - 1);
                var y = Math.Clamp(py + dy, 0, DiffuseSize - 1);
                unsafe
                {
                    var row = (ushort*)((byte*)map.DataPointer + y * map.RowPitch);
                    var r = (float)BitConverter.UInt16BitsToHalf(row[x * 4 + 0]);
                    var g = (float)BitConverter.UInt16BitsToHalf(row[x * 4 + 1]);
                    var b = (float)BitConverter.UInt16BitsToHalf(row[x * 4 + 2]);
                    sum += 0.2126f * r + 0.7152f * g + 0.0722f * b;
                }
                n++;
            }
            return MathF.PI * sum / n;
        }
        finally
        {
            context.Unmap(staging, 0);
        }
    }

    public Environment(ID3D11Device device, ID3D11DeviceContext context, string hdrPath, Vector3 dialNormalInEnv)
    {
        var sw = Stopwatch.StartNew();
        var (width, height, pixels) = ReadRadianceHdr(hdrPath);

        // ---- the panorama, with mips so the prefilter can sample it blurred
        using var equirect = device.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)width, Height = (uint)height, MipLevels = 0, ArraySize = 1,
            Format = Format.R16G16B16A16_Float, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Default,
            BindFlags = BindFlags.ShaderResource | BindFlags.RenderTarget,
            MiscFlags = ResourceOptionFlags.GenerateMips,
        });
        context.UpdateSubresource<Half>(pixels, equirect, 0, (uint)(width * 8), 0);
        using var equirectSrv = device.CreateShaderResourceView(equirect);
        context.GenerateMips(equirectSrv);

        // ---- shaders and state for the four bakes
        using var vsBlob = Gpu.Compile("ibl.hlsl", "VsFullscreen", "vs_5_0");
        using var vs = device.CreateVertexShader(vsBlob.AsBytes());
        using var psEquirect = CreatePs(device, "PsEquirect");
        using var psPrefilter = CreatePs(device, "PsPrefilter");
        using var psIrradiance = CreatePs(device, "PsIrradiance");
        using var psBrdf = CreatePs(device, "PsBrdf");
        using var cb = Gpu.CreateConstantBuffer<Params>(device);
        using var sampler = device.CreateSamplerState(new SamplerDescription(Filter.MinMagMipLinear,
            TextureAddressMode.Clamp, TextureAddressMode.Clamp, TextureAddressMode.Clamp));
        using var raster = device.CreateRasterizerState(RasterizerDescription.CullNone);
        using var depth = device.CreateDepthStencilState(DepthStencilDescription.None);

        context.IASetInputLayout(null);
        context.IASetPrimitiveTopology(PrimitiveTopology.TriangleList);
        context.VSSetShader(vs);
        context.PSSetSampler(0, sampler);
        context.PSSetConstantBuffer(0, cb);
        context.RSSetState(raster);
        context.OMSetDepthStencilState(depth);
        context.OMSetBlendState(null);

        // ---- source cube: the panorama as a cube map, with a full mip chain
        using var source = CreateCube(device, SpecularSize, 0, true);
        using var sourceSrv = device.CreateShaderResourceView(source);
        context.PSSetShader(psEquirect);
        context.PSSetShaderResource(0, equirectSrv);
        for (var face = 0; face < 6; face++)
        {
            using var rtv = FaceView(device, source, face, 0);
            context.OMSetRenderTargets(rtv);
            context.RSSetViewport(0, 0, SpecularSize, SpecularSize);
            context.UpdateSubresource(new Params { Face = face }, cb);
            context.Draw(3, 0);
        }
        context.OMSetRenderTargets((ID3D11RenderTargetView?)null);
        context.GenerateMips(sourceSrv);

        // ---- specular: one mip per roughness step
        _specularTex = CreateCube(device, SpecularSize, SpecularMips, false);
        Specular = device.CreateShaderResourceView(_specularTex);
        context.PSSetShader(psPrefilter);
        context.PSSetShaderResource(1, sourceSrv);
        for (var mip = 0; mip < SpecularMips; mip++)
        {
            var size = SpecularSize >> mip;
            var roughness = mip / (float)(SpecularMips - 1);
            for (var face = 0; face < 6; face++)
            {
                using var rtv = FaceView(device, _specularTex, face, mip);
                context.OMSetRenderTargets(rtv);
                context.RSSetViewport(0, 0, size, size);
                context.UpdateSubresource(new Params
                {
                    Face = face, Roughness = roughness, SourceSize = SpecularSize,
                    Samples = mip == 0 ? 1 : 256,
                }, cb);
                context.Draw(3, 0);
            }
        }

        // ---- diffuse
        _diffuseTex = CreateCube(device, DiffuseSize, 1, false);
        Diffuse = device.CreateShaderResourceView(_diffuseTex);
        context.PSSetShader(psIrradiance);
        for (var face = 0; face < 6; face++)
        {
            using var rtv = FaceView(device, _diffuseTex, face, 0);
            context.OMSetRenderTargets(rtv);
            context.RSSetViewport(0, 0, DiffuseSize, DiffuseSize);
            context.UpdateSubresource(new Params { Face = face }, cb);
            context.Draw(3, 0);
        }

        // ---- the calibration read-back: see IrradianceUnits
        IrradianceUnits = ReadIrradiance(device, context, _diffuseTex, dialNormalInEnv);

        // ---- the BRDF table
        _lutTex = device.CreateTexture2D(new Texture2DDescription
        {
            Width = LutSize, Height = LutSize, MipLevels = 1, ArraySize = 1,
            Format = Format.R16G16_Float, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Default,
            BindFlags = BindFlags.ShaderResource | BindFlags.RenderTarget,
        });
        BrdfLut = device.CreateShaderResourceView(_lutTex);
        using (var rtv = device.CreateRenderTargetView(_lutTex))
        {
            context.PSSetShader(psBrdf);
            context.OMSetRenderTargets(rtv);
            context.RSSetViewport(0, 0, LutSize, LutSize);
            context.Draw(3, 0);
        }

        context.OMSetRenderTargets((ID3D11RenderTargetView?)null);
        context.PSSetShaderResource(0, null);
        context.PSSetShaderResource(1, null);
        context.Flush();
        Debug.WriteLine($"[ClockWall] environment baked in {sw.ElapsedMilliseconds} ms from {Path.GetFileName(hdrPath)} {width}x{height}");
    }

    private static ID3D11PixelShader CreatePs(ID3D11Device device, string entry)
    {
        using var blob = Gpu.Compile("ibl.hlsl", entry, "ps_5_0");
        return device.CreatePixelShader(blob.AsBytes());
    }

    private static ID3D11Texture2D CreateCube(ID3D11Device device, int size, int mips, bool generateMips)
    {
        return device.CreateTexture2D(new Texture2DDescription
        {
            Width = (uint)size, Height = (uint)size, MipLevels = (uint)mips, ArraySize = 6,
            Format = Format.R16G16B16A16_Float, SampleDescription = new SampleDescription(1, 0),
            Usage = ResourceUsage.Default,
            BindFlags = BindFlags.ShaderResource | BindFlags.RenderTarget,
            MiscFlags = ResourceOptionFlags.TextureCube | (generateMips ? ResourceOptionFlags.GenerateMips : ResourceOptionFlags.None),
        });
    }

    private static ID3D11RenderTargetView FaceView(ID3D11Device device, ID3D11Texture2D cube, int face, int mip)
    {
        return device.CreateRenderTargetView(cube, new RenderTargetViewDescription
        {
            Format = Format.R16G16B16A16_Float,
            ViewDimension = RenderTargetViewDimension.Texture2DArray,
            Texture2DArray = new Texture2DArrayRenderTargetView
            {
                MipSlice = (uint)mip, FirstArraySlice = (uint)face, ArraySize = 1,
            },
        });
    }

    /// <summary>
    /// Reads a Radiance .hdr (RGBE, new-style run-length encoded scanlines)
    /// into half-float RGBA. Forty lines, because the format is forty lines:
    /// a text header, a resolution line, then per scanline four channels each
    /// run-length coded. Pulling in an image library for this would be the
    /// larger dependency by a wide margin.
    /// </summary>
    private static (int Width, int Height, Half[] Pixels) ReadRadianceHdr(string path)
    {
        var data = File.ReadAllBytes(path);
        var pos = 0;

        string ReadLine()
        {
            var start = pos;
            while (pos < data.Length && data[pos] != '\n') pos++;
            var line = System.Text.Encoding.ASCII.GetString(data, start, pos - start);
            pos++;
            return line;
        }

        var magic = ReadLine();
        if (!magic.StartsWith("#?", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{path} is not a Radiance HDR");
        }

        string line;
        do { line = ReadLine(); } while (line.Length > 0);

        var res = ReadLine().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        // "-Y h +X w": rows top to bottom, columns left to right. Anything
        // else is a rotated file, which no HDRI we would ship is.
        if (res.Length != 4 || res[0] != "-Y" || res[2] != "+X")
        {
            throw new InvalidDataException($"unsupported HDR orientation '{string.Join(' ', res)}'");
        }

        var height = int.Parse(res[1]);
        var width = int.Parse(res[3]);
        var pixels = new Half[width * height * 4];
        var scan = new byte[width * 4];

        for (var y = 0; y < height; y++)
        {
            if (data[pos] == 2 && data[pos + 1] == 2 && (data[pos + 2] << 8 | data[pos + 3]) == width)
            {
                pos += 4;
                for (var c = 0; c < 4; c++)
                {
                    var x = 0;
                    while (x < width)
                    {
                        var count = data[pos++];
                        if (count > 128)
                        {
                            count -= 128;
                            var value = data[pos++];
                            for (var k = 0; k < count; k++) scan[(x++) * 4 + c] = value;
                        }
                        else
                        {
                            for (var k = 0; k < count; k++) scan[(x++) * 4 + c] = data[pos++];
                        }
                    }
                }
            }
            else
            {
                // Flat scanline - old files, or very narrow ones.
                Array.Copy(data, pos, scan, 0, width * 4);
                pos += width * 4;
            }

            for (var x = 0; x < width; x++)
            {
                var e = scan[x * 4 + 3];
                var o = (y * width + x) * 4;
                if (e == 0)
                {
                    pixels[o] = pixels[o + 1] = pixels[o + 2] = (Half)0f;
                }
                else
                {
                    var f = MathF.ScaleB(1f, e - 136);
                    pixels[o] = (Half)(scan[x * 4] * f);
                    pixels[o + 1] = (Half)(scan[x * 4 + 1] * f);
                    pixels[o + 2] = (Half)(scan[x * 4 + 2] * f);
                }

                pixels[o + 3] = (Half)1f;
            }
        }

        return (width, height, pixels);
    }

    public void Dispose()
    {
        Specular.Dispose();
        Diffuse.Dispose();
        BrdfLut.Dispose();
        _specularTex.Dispose();
        _diffuseTex.Dispose();
        _lutTex.Dispose();
    }
}
