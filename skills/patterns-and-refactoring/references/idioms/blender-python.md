# Blender · bpy · procedural assets

[← back to router](../framework-idioms.md)

Driving Blender from code fails differently from ordinary software. Python errors are rare; the
expensive failures are silent or visual, and they surface after a long render. So verification
carries more weight here than class structure, and most entries below are about proving what
you built.

---

## What Blender already gives you

| Pattern | Where it lives | Do this, not that |
|---|---|---|
| **Decorator** | The modifier stack | Non-destructive and ordered. Read the result from the evaluated object, not `obj.data` |
| **Prototype + Flyweight** | Shared mesh data; collection instances | Link one mesh into many objects. Hundreds of copies of the same detail belong in instances or one merged mesh |
| **Pipes and Filters** | Geometry Nodes; shader and compositor node trees | Prefer a node group over a hand-written mesh loop when the result must stay editable |
| **Composite** | Collections and parenting | A collection is also the unit of ownership: a script deletes what it owns, and nothing else |
| **Template Method** | A `.blend` template plus a per-asset script | Shared lights, camera and settings live in the template; `blender -b template.blend --python asset.py` |
| **Proxy** | Library linking; `bpy.data.libraries.load` | Reference heavy parts while judging renders, strip them before export |
| **Observer** | Drivers and handlers | Convenient live, but drivers do not survive a glTF export: bake them |
| **Facade** | A small shared helper module | One owner. Workers report defects instead of patching around them locally |

---

## The operator or data API question

**`bpy.ops` is justified when** an operator does what no data call does (booleans applied,
bakes, exports) and you can give it context explicitly with `temp_override`.

**The data API is justified when** you create or read many things: it needs no selection state
and no active object, and it runs in background mode unchanged.

Neither is a rule. Heavy use of `bpy.ops` with explicit context did not produce a pattern of
failures; what did fail were scripts relying on context after a file load, where
`bpy.context.window` can also be `None` in background mode. Split the file switch and the export
into separate calls, and keep helpers on disk rather than in session memory.

---

## Keep generators re-runnable

One script per asset, safe to run twice.

- **Own what you delete.** Remove by collection or name prefix. A generic "clear the scene" has
  deleted cameras and animation that belonged to someone else.
- **Build new, then swap.** Removing items in place from a reused scene or sequencer fails in
  ways a fresh container does not.
- **Get-or-create still sets every value.** An early `return` after `bpy.data.materials.get()`
  keeps stale parameters on every rebuild:

```python
mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
# set every input here, on both paths
```

- **Never swallow a failed assignment.** Node settings move between versions, some of them onto
  menu input sockets. A `try/except` around `setattr` leaves the old value in place without a
  word. Assign, then read the value back.
- **Probe the API of the running version.** Read enum identifiers from `bl_rna` rather than
  hard-coding them, and look shader nodes up by `type`, because names are localized.

---

## Prove it, from the delivery camera

| Check | Why |
|---|---|
| **Render a low-sample frame through the final camera before any expensive step** | Close-ups pass while the real view fails. Whole scenes can vanish behind one setting |
| **Set `clip_end` for the scene** | The default is 100 m. A landscape then renders as empty sky while its reflection still shows, and a far-clip arc can pass for a glass artefact |
| **Point generated normals outwards** | A code-built surface with flipped winding renders as seen from inside. Water then shows total internal reflection: a hard edge near 49 degrees of incidence |
| **Compare polygons before and after a boolean** | A cut can do nothing, or return an empty mesh that surfaces only as an exporter warning |
| **Measure instead of squinting** | Dot products for facing, `world_to_camera_view` for framing, `evaluated_get` for real triangle counts, pixel samples for colour |
| **Isolate before fixing an artefact** | Hide suspects, render flat. Guessed causes are usually wrong: a smudge can be a helper's shadow, and dirt can be a bake halo |
| **Read the exported file back** | Custom properties need `export_extras`; drivers do not export. Parse the GLB or load it in the target runtime |
| **Check handedness in a render** | Z-up, rear views and text all produce believable mirrored results |

Booleans, with the failure made loud:

```python
mod = obj.modifiers.new("Cut", "BOOLEAN")
mod.operation, mod.object = "DIFFERENCE", cutter
depsgraph = bpy.context.evaluated_depsgraph_get()
if not len(obj.evaluated_get(depsgraph).data.polygons):
    raise RuntimeError("cut emptied the mesh")
```

---

## Long jobs

- **Run them headless.** A long call into a live session can drop its connection while the job
  keeps running. Treat a disconnect as unknown, not failed, and look for the output before
  repeating work.
- **Give each parallel worker its own process and file.** A live Blender holds one scene.
- **Propagate failures.** Use `--python-exit-code 1`. Without it, and with output piped through a
  filter, a Python error can look like success.
- **Render sequences to frames and encode separately.** Long jobs get killed; finished frames
  survive. Delete zero-byte frames before resuming, or a resume skips them.
- **Read the render log.** A render can complete with a logged memory overflow in it.
- **Name the scene explicitly.** A context override does not change which scene is rendered:
  use `blender -b file -S scene`.
- **Time one frame before committing to a sequence**, and test the encoder on a tiny one.
- **Watch memory, and stop only your own jobs.** A failed allocation can leave a hung process
  holding the RAM. Build expensive data outside Blender when a small script can compute it.

---

## When the camera never moves

When the viewer cannot move, detail belongs where it lands on screen, not evenly in the world.

- **A polar grid centred on the camera, spaced logarithmically,** gives constant density on
  screen: near ground and far ridges receive the same pixels per triangle.
- **Spend nothing on what cannot be seen.** Back faces of distant ranges can stay coarse.
- **The cost:** the asset is no longer valid from anywhere else. Moving the camera later means
  rebuilding the mesh. That is the trade, so state it in the decision.
- **Bake what stays still, compute what moves.** Stretching a rendered image to animate it shows
  its pixels. A shader that derives the surface point from the view direction stays sharp.

---

## Natural surfaces

- **Rock is planes, not noise.** Erosion alone gives rounded clay. Replacing each Voronoi cell with
  the tangent plane at its seed, coarse to fine, gives real faces and sharp edges. Cap the plane
  slope, or snow has nowhere to settle.
- **Do not measure cliffs from above.** Noise sampled on x and y smears down steep walls. Sample
  it along the wall, using height as one axis.
- **Keep detail above the mesh's sampling limit.** Height detail finer than the spacing combs.
  Put it in the material, where it is evaluated per pixel.
- **Light from the side.** A sun behind the camera flattens any relief.

## Signs you are working against the tool

- Geometry written from memory of an object rather than from references or real dimensions.
- Scale carried in node setups instead of UVs: metres divided by texture size survives export.
- A material per part when a merge by material would cut the file size by an order of magnitude.
- A helper library patched privately by each worker.
- Camera parented to a scaled object, with its `matrix_world` never checked.
- Concave outlines filled as a single n-gon, which fills the convex hull and shows only in renders.
- Triangle budgets printed but never enforced.

---

## Sources

Blender Python API reference and manual, version 5.2. Lessons distilled from working sessions
across several projects on Blender 5.2 and Windows; treat version-specific behaviour accordingly.
Original commentary.
