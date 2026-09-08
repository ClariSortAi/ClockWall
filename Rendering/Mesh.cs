using System;
using Vortice.Direct3D11;

namespace ClockWall.Rendering;

/// <summary>One drawable: a vertex buffer, an index buffer, and a count.
/// Every mesh in the watch comes out of a GLB written by tools/ - the OM10
/// movement, the case solids - and none is built in code.</summary>
internal sealed class Mesh : IDisposable
{
    public ID3D11Buffer Vertices { get; }
    public ID3D11Buffer Indices { get; }
    public uint IndexCount { get; }

    public Mesh(ID3D11Device device, ReadOnlySpan<Gpu.Vertex> vertices, ReadOnlySpan<uint> indices)
    {
        Vertices = Gpu.CreateVertexBuffer(device, vertices);
        Indices = Gpu.CreateIndexBuffer(device, indices);
        IndexCount = (uint)indices.Length;
    }

    public void Draw(ID3D11DeviceContext context)
    {
        context.IASetVertexBuffer(0, Vertices, Gpu.Vertex.Stride);
        context.IASetIndexBuffer(Indices, Vortice.DXGI.Format.R32_UInt, 0);
        context.DrawIndexed(IndexCount, 0, 0);
    }

    public void Dispose()
    {
        Vertices.Dispose();
        Indices.Dispose();
    }
}
