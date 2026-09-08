using System;
using System.Collections.Generic;
using System.Numerics;
using Vortice.Direct3D11;

namespace ClockWall.Rendering;

/// <summary>One drawable: a vertex buffer, an index buffer, and a count.</summary>
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

/// <summary>
/// The parts of the watch that are not the movement: case, bezel, rehaut,
/// dial, indices, hands, cap, crystal. All of it is built here from numbers,
/// in millimetres, in the world frame the scene uses - X to the right, Y
/// toward the viewer, Z down the dial toward six.
///
/// WHY PROCEDURAL AND NOT A SECOND GLB. These are lathes and extrusions with
/// a handful of dimensions each, and the dimensions are the proportions
/// tools/case_geometry.py already settled in face units. Rebuilding them from
/// the same numbers keeps the two faces the same object; loading a second
/// exported asset would freeze a proportion the moment somebody wanted to move
/// a bezel by a hair. Normals are analytic - flat for a facet, radial for a
/// curve - so nothing here averages a corner into a black sliver.
/// </summary>
internal sealed class MeshBuilder
{
    private readonly List<Gpu.Vertex> _v = new();
    private readonly List<uint> _i = new();

    public Mesh Build(ID3D11Device device) => new(device, _v.ToArray(), _i.ToArray());

    public int VertexCount => _v.Count;

    // ------------------------------------------------------------ primitives

    /// <summary>One flat triangle, normal from its winding (counter-clockwise
    /// seen from outside).</summary>
    public void Triangle(Vector3 a, Vector3 b, Vector3 c)
    {
        var n = Vector3.Normalize(Vector3.Cross(b - a, c - a));
        var baseIndex = (uint)_v.Count;
        _v.Add(new Gpu.Vertex { Position = a, Normal = n });
        _v.Add(new Gpu.Vertex { Position = b, Normal = n });
        _v.Add(new Gpu.Vertex { Position = c, Normal = n });
        _i.Add(baseIndex); _i.Add(baseIndex + 1); _i.Add(baseIndex + 2);
    }

    /// <summary>One flat quad, a-b-c-d counter-clockwise from outside.</summary>
    public void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d)
    {
        Triangle(a, b, c);
        Triangle(a, c, d);
    }

    /// <summary>A convex polygon lying flat, fanned from its first vertex. The
    /// polygon is given counter-clockwise when seen from the side its normal
    /// faces.</summary>
    public void ConvexPolygon(IReadOnlyList<Vector3> pts)
    {
        for (var k = 1; k + 1 < pts.Count; k++)
        {
            Triangle(pts[0], pts[k], pts[k + 1]);
        }
    }

    // ------------------------------------------------------------ lathe

    /// <summary>A point on a lathe profile: radius, height, and the profile's
    /// outward normal there. Repeat a point with two different normals to
    /// make a sharp edge.</summary>
    public readonly record struct ProfilePoint(float R, float Y, float Nr, float Ny);

    /// <summary>
    /// A straight run between two profile points with a flat normal. The
    /// profile is walked in the direction that keeps the outside on the
    /// right when going from p0 to p1 - i.e. give the outer surface of a
    /// solid from bottom to top, and a bore from top to bottom.
    /// </summary>
    public static void Line(List<ProfilePoint> profile, Vector2 p0, Vector2 p1)
    {
        var d = Vector2.Normalize(p1 - p0);
        var n = new Vector2(d.Y, -d.X);
        profile.Add(new ProfilePoint(p0.X, p0.Y, n.X, n.Y));
        profile.Add(new ProfilePoint(p1.X, p1.Y, n.X, n.Y));
    }

    /// <summary>A circular arc of the profile about <paramref name="centre"/>,
    /// with radial normals - a fillet or a dome.</summary>
    public static void Arc(List<ProfilePoint> profile, Vector2 centre, float radius, float fromDeg, float toDeg, int steps, bool concave = false)
    {
        for (var k = 0; k <= steps; k++)
        {
            var a = MathF.PI / 180f * (fromDeg + (toDeg - fromDeg) * k / steps);
            var n = new Vector2(MathF.Cos(a), MathF.Sin(a));
            var p = centre + n * radius;
            if (concave) n = -n;
            profile.Add(new ProfilePoint(p.X, p.Y, n.X, n.Y));
        }
    }

    /// <summary>Revolves a profile about the vertical axis through
    /// (cx, cz). Consecutive profile points become one ring of quads; a
    /// repeated point with a different normal is a crease.</summary>
    public void Lathe(IReadOnlyList<ProfilePoint> profile, int segments, float cx = 0, float cz = 0)
    {
        var baseIndex = (uint)_v.Count;
        for (var s = 0; s <= segments; s++)
        {
            var a = MathF.Tau * s / segments;
            var (sin, cos) = MathF.SinCos(a);
            foreach (var p in profile)
            {
                _v.Add(new Gpu.Vertex
                {
                    Position = new Vector3(cx + p.R * cos, p.Y, cz + p.R * sin),
                    Normal = Vector3.Normalize(new Vector3(p.Nr * cos, p.Ny, p.Nr * sin)),
                });
            }
        }

        var n = profile.Count;
        for (var s = 0; s < segments; s++)
        {
            for (var k = 0; k + 1 < n; k++)
            {
                var a = profile[k];
                var b = profile[k + 1];
                // A repeated point is a crease, not a face.
                if (MathF.Abs(a.R - b.R) < 1e-6f && MathF.Abs(a.Y - b.Y) < 1e-6f) continue;

                var i0 = baseIndex + (uint)(s * n + k);
                var i1 = baseIndex + (uint)(s * n + k + 1);
                var i2 = baseIndex + (uint)((s + 1) * n + k + 1);
                var i3 = baseIndex + (uint)((s + 1) * n + k);
                // Winding follows the "outside on the right" rule of Line.
                _i.Add(i0); _i.Add(i1); _i.Add(i2);
                _i.Add(i0); _i.Add(i2); _i.Add(i3);
            }
        }
    }

    // ------------------------------------------------------------ prisms

    /// <summary>
    /// A convex outline in the XZ plane extruded from y0 to y1, with the
    /// top edge chamfered by <paramref name="chamfer"/>. Applied indices and
    /// the second hand's needle are this. The outline is given clockwise as
    /// seen from above (+Y), i.e. clockwise on the dial.
    /// </summary>
    public void ChamferedPrism(IReadOnlyList<Vector2> outline, float y0, float y1, float chamfer)
    {
        // The winding is checked, not trusted. The batons were handed in
        // counter-clockwise once and every index on the dial quietly faced
        // its top downward - dull grey where it should have been the
        // brightest thing on the watch, and nothing in the build to say why.
        var area = 0f;
        for (var k = 0; k < outline.Count; k++)
        {
            var a = outline[k]; var b = outline[(k + 1) % outline.Count];
            area += a.X * b.Y - b.X * a.Y;
        }
        if (area < 0)
        {
            var reversed = new List<Vector2>(outline);
            reversed.Reverse();
            outline = reversed;
        }

        var n = outline.Count;
        var inset = Inset(outline, chamfer);
        var yb = y1 - chamfer;

        // Top: the inset outline, flat.
        var top = new List<Vector3>(n);
        for (var k = n - 1; k >= 0; k--) top.Add(new Vector3(inset[k].X, y1, inset[k].Y));
        ConvexPolygon(top);

        for (var k = 0; k < n; k++)
        {
            var j = (k + 1) % n;
            var o0 = outline[k]; var o1 = outline[j];
            var i0 = inset[k]; var i1 = inset[j];
            // Bevel band from the crease at yb up to the top's inset edge.
            Quad(new Vector3(o1.X, yb, o1.Y), new Vector3(o0.X, yb, o0.Y),
                 new Vector3(i0.X, y1, i0.Y), new Vector3(i1.X, y1, i1.Y));
            // Wall.
            Quad(new Vector3(o1.X, y0, o1.Y), new Vector3(o0.X, y0, o0.Y),
                 new Vector3(o0.X, yb, o0.Y), new Vector3(o1.X, yb, o1.Y));
        }
    }

    /// <summary>Offsets a convex clockwise-from-above outline inward by d.</summary>
    private static Vector2[] Inset(IReadOnlyList<Vector2> outline, float d)
    {
        var n = outline.Count;
        var result = new Vector2[n];
        for (var k = 0; k < n; k++)
        {
            var prev = outline[(k + n - 1) % n];
            var cur = outline[k];
            var next = outline[(k + 1) % n];
            var e0 = Vector2.Normalize(cur - prev);
            var e1 = Vector2.Normalize(next - cur);
            // Inward normals for a clockwise outline in a Y-down plane. The
            // XZ plane seen from +Y has X right and Z down-the-dial, so
            // "clockwise from above" is the same handedness as the dial.
            var n0 = new Vector2(-e0.Y, e0.X);
            var n1 = new Vector2(-e1.Y, e1.X);
            var bis = Vector2.Normalize(n0 + n1);
            var cosHalf = Vector2.Dot(bis, n0);
            result[k] = cur + bis * (d / MathF.Max(cosHalf, 0.2f));
        }

        return result;
    }

    // ------------------------------------------------------------ the hands

    /// <summary>
    /// A dauphine hand: a faceted kite with a ridge down its length, tip at
    /// -Z (twelve o'clock), pivot at the origin. The two facets meet at the
    /// ridge, which is the whole hand - a bright line on one side and a dark
    /// one on the other that swap as the hand crosses the light. Base at
    /// <paramref name="y0"/>, ridge at <paramref name="y0"/> + <paramref name="ridge"/>.
    /// </summary>
    public void Dauphine(float length, float halfWidth, float shoulder, float tail, float y0, float ridge)
    {
        var tip = new Vector2(0, -length);
        var lSh = new Vector2(-halfWidth, -shoulder);
        var rSh = new Vector2(halfWidth, -shoulder);
        var lTl = new Vector2(-halfWidth * 0.34f, tail);
        var rTl = new Vector2(halfWidth * 0.34f, tail);
        var cTl = new Vector2(0, tail);

        var yr = y0 + ridge;
        Vector3 At(Vector2 p, float y) => new(p.X, y, p.Y);

        // The ridge does not stay at full height to the very tip - the
        // facets converge before the point does - so the tip sits low.
        var tipY = y0 + ridge * 0.25f;

        // Left facet (x < 0): tip, ridge-tail, left tail, left shoulder.
        Triangle(At(tip, tipY), At(lSh, y0), At(cTl, yr));
        Triangle(At(lSh, y0), At(lTl, y0), At(cTl, yr));
        // Right facet.
        Triangle(At(tip, tipY), At(cTl, yr), At(rSh, y0));
        Triangle(At(rSh, y0), At(cTl, yr), At(rTl, y0));

        // Walls, from the outline at y0 down to the underside, and the
        // underside itself. Thin, but the tilt of the view shows them.
        var floor = y0 - ridge * 0.6f;
        Vector2[] outline = { tip, rSh, rTl, lTl, lSh };
        for (var k = 0; k < outline.Length; k++)
        {
            var a = outline[k]; var b = outline[(k + 1) % outline.Length];
            Quad(At(b, floor), At(a, floor), At(a, y0), At(b, y0));
        }
        var under = new List<Vector3>();
        for (var k = outline.Length - 1; k >= 0; k--) under.Add(At(outline[k], floor));
        under.Reverse();
        ConvexPolygon(under);
    }
}
