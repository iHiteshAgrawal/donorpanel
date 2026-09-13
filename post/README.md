# builder.aws.com post

| File | What it is |
| --- | --- |
| `agents-for-humans.md` | The article. Paste into the editor as is |
| `figures.html` | Source for every rendered figure and the cover |
| `render_figures.py` | Element level capture to `figures/<name>.png` |
| `figures/` | The images to upload |

## Publishing

The editor's markdown supports headings, bold, italic, inline code, fenced code blocks, ordered
and unordered lists, and links. **It does not document pipe tables**, which is why every table in
this post is a rendered image rather than markup.

1. Regenerate the figures if anything changed:

   ```
   uv run python post/render_figures.py
   ```

2. Paste `agents-for-humans.md` into the editor.
3. Upload `figures/cover.png` as the article cover image.
4. Work down the article. Each figure position is marked by a line beginning `> FIGURE:`. Upload
   that image there, then **delete the placeholder line** and keep the caption line under it as
   plain text.

There are four figure positions, in order:

1. `cover.png` at the top, also used as the article cover
2. `architecture-runtime.png` under **The architecture**
3. `architecture-graph.png` immediately after it
4. `graph-strip.png` opening **Five Strands patterns you can lift**

`architecture.png` is the whole diagram in one image, kept as a spare. The two halves are the
default because the full one is dense at article width.

### If an upload is rejected as inappropriate

It happened here. The architecture diagram was refused until the **tools panel** was painted out,
and the result is counter-intuitive enough to be worth recording:

- the tools panel **on its own** uploaded fine
- the diagram **without** the panel uploaded fine
- the diagram **with** the panel was refused

So the panel is not independently objectionable. It only trips the filter in combination with the
rest of the image, which points at OCR: alone it yields two `blood` tokens, but the whole diagram
also yields *Donor*, *User*, *Human Intervention Required* and *close (rejected)*, and that
aggregate is what a crude keyword classifier misreads.

Every export in `figures/` has the panel removed, which costs nothing because the ten tool names
are already listed in the article as markdown.

Bisect rather than guess if it happens again. Upload one suspect at a time, a panel or an icon or
half the diagram. Four uploads located this, and the first hypothesis (a Google wordmark in the
browser icon) was wrong. The wordmark is painted out of these exports anyway, since a third party
trademark does not belong in an AWS architecture diagram, but it was not the cause.

## Why only three images

Text baked into a PNG cannot be read by a screen reader, does not reflow on a phone, is not
searchable, and is not indexed. An early draft had ten figures and most of them were tables
wearing a costume: inventories, comparison panes, bullet lists rendered as pictures.

The rule that replaced them: **a diagram earns an image, a table does not.** What survived is the
cover, the architecture diagram, and the node strip, because in all three the spatial arrangement
carries meaning that prose would lose. Everything else moved into the article as real markdown
lists, which is longer to read but accessible, selectable and indexable.

One figure was going to be a two bar chart of 196 invocations against 3,737 throttles. It is a
single headline comparison, so the right form is a sentence in bold, not a chart.

## Rendering notes

Figures are captured at their own bounding box, not through a fixed viewport, so each one is sized
by its content. `--scale 2` is the default, giving 3200px wide files for 1600px designs, which
stay crisp when the platform scales them down.

Two constraints learned by looking at the output rather than assuming:

- **Wide beats tall.** The two inventory figures started as single columns at 1600x1685 and the
  text would have halved in size inline. Two columns brought them to roughly 1600x1100.
- **Fonts must be loaded before capture.** `render_figures.py` waits on `document.fonts.status`,
  because a figure captured early renders in a fallback face and it is obvious the moment two
  figures sit next to each other.

To re-render one figure while iterating:

```
uv run python post/render_figures.py --only strands-map
```

## Before publishing

- Title contains **Agents for Humans**.
- Every code block is copied from the repository. A checker was run over all thirteen and all
  matched their source files exactly; re-run it if the code changes.
- No em dashes.
- Open each figure at the width the platform displays it and confirm the smallest text is legible.
