using System;
using System.Collections.Generic;
using System.Numerics;
using SharpGLTF.Schema2;
using Vortice.Direct3D11;

namespace ClockWall.Rendering;

/// <summary>
/// Reads captures/gltf/movement.glb - the 23 named OM10 parts - into one
/// <see cref="Mesh"/> per part, keyed by the exporter's names.
///
/// The asset is already assembled: tools/gltf_export.py translates each part
/// to its arbor and its height in the stack, converts to Y-up, and writes
/// analytic surface normals. So there is nothing to do here but copy
/// positions and normals across and keep the names, and specifically nothing
/// to rotate - see HANDOVER-REALTIME.md on the sideways import that a
/// consumer "helpfully" correcting the axes produces.
/// </summary>
internal static class GltfLoader
{
    public static Dictionary<string, Mesh> Load(ID3D11Device device, string path)
    {
        var model = ModelRoot.Load(path);
        var result = new Dictionary<string, Mesh>(StringComparer.Ordinal);

        foreach (var node in model.DefaultScene.VisualChildren)
        {
            if (node.Mesh is null) continue;
            var name = node.Name ?? node.Mesh.Name ?? $"node{node.LogicalIndex}";

            // Node transforms are identity in this asset, but honouring them
            // costs one multiply per vertex and protects against an exporter
            // that starts writing them.
            var world = node.WorldMatrix;
            var normalXf = Matrix4x4.Identity;
            if (Matrix4x4.Invert(world, out var inv)) normalXf = Matrix4x4.Transpose(inv);

            var verts = new List<Gpu.Vertex>();
            var indices = new List<uint>();

            foreach (var prim in node.Mesh.Primitives)
            {
                var positions = prim.GetVertexAccessor("POSITION").AsVector3Array();
                var normals = prim.GetVertexAccessor("NORMAL")?.AsVector3Array();
                var baseIndex = (uint)verts.Count;

                for (var k = 0; k < positions.Count; k++)
                {
                    var n = normals is not null ? normals[k] : Vector3.UnitY;
                    verts.Add(new Gpu.Vertex
                    {
                        Position = Vector3.Transform(positions[k], world),
                        Normal = Vector3.Normalize(Vector3.TransformNormal(n, normalXf)),
                    });
                }

                foreach (var (a, b, c) in prim.GetTriangleIndices())
                {
                    indices.Add(baseIndex + (uint)a);
                    indices.Add(baseIndex + (uint)b);
                    indices.Add(baseIndex + (uint)c);
                }
            }

            result[name] = new Mesh(device, verts.ToArray(), indices.ToArray());
        }

        return result;
    }
}
