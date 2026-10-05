"""DOT text generation without pygraphviz.

``build_dot`` is the single graph builder: the CLI writes its string to
a file, the web page renders it with viz.js, and the local server hands
it to Graphviz for PNG and TikZ exports.
"""


class HtmlLabel(str):
    """A Graphviz HTML-like label (emitted as <...>, not quoted)."""


def _q(s):
    """Quote a DOT identifier or attribute value."""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _attrs(d):
    parts = []
    for k, v in d.items():
        if isinstance(v, HtmlLabel):
            parts.append(f"{k}={v}")      # HTML-like label, unquoted
        else:
            parts.append(f"{k}={_q(v)}")  # plain text, always quoted
    return ", ".join(parts)


def build_dot(nodes, edges, env_config, cycle_edges=None,
              section_assignments=None, filter_sections=None,
              filter_envs=None, view_mode="macro", micro_section=None,
              add_legend=True, rankdir=None):
    """Return DOT source for the graph.  The macro view is flat (no clusters).

    Parameters:
        nodes: list[NodeInfo]
        edges: list[DependencyEdge]
        env_config: {env_name -> {"shape", "border", "fill"}}
        cycle_edges: set of (source, target) keys drawn in red
        section_assignments: {label -> section_title} (optional)
        filter_sections: set of section titles to include (optional)
        filter_envs: set of env names to include (None = all configured)
        view_mode: "macro" or "micro"
        micro_section: section title for the micro view; nodes outside it
            that touch an included node are drawn as grey "ghost" nodes
        add_legend: append the legend node
        rankdir: optional Graphviz rankdir ("TB", "LR", ...)
    """
    if cycle_edges is None:
        cycle_edges = set()
    if section_assignments is None:
        section_assignments = {}
    micro = view_mode == "micro" and bool(micro_section)

    included = []
    for ni in nodes:
        if ni.env not in env_config:
            continue
        if filter_envs is not None and ni.env not in filter_envs:
            continue
        sec = section_assignments.get(ni.label, "(ungrouped)")
        if filter_sections and sec not in filter_sections:
            continue
        if micro and sec != micro_section:
            continue
        included.append(ni)
    visible = {ni.label for ni in included}

    ghosts = []
    if micro:
        label_to_ni = {ni.label: ni for ni in nodes}
        ghost_labels = set()
        for e in edges:
            if e.source in visible and e.target not in visible:
                ghost_labels.add(e.target)
            if e.target in visible and e.source not in visible:
                ghost_labels.add(e.source)
        ghosts = [label_to_ni[l] for l in ghost_labels if l in label_to_ni]
        visible |= {ni.label for ni in ghosts}

    lines = ["digraph knowtex {"]
    graph_attrs = {"bgcolor": "transparent"}
    if rankdir:
        graph_attrs["rankdir"] = rankdir
    lines.append(f"  graph [{_attrs(graph_attrs)}];")
    lines.append("  node [penwidth=1.8];")
    lines.append("  edge [arrowhead=vee];")

    for ni in included:
        cfg = env_config.get(ni.env, {})
        attrs = {
            "label": ni.display_name,
            "shape": cfg.get("shape", "ellipse"),
            "style": "filled",
            "color": cfg.get("border", "black"),
            "fillcolor": cfg.get("fill", "white"),
            "URL": ni.label,
            "tooltip": ni.label,
        }
        lines.append(f"  {_q(ni.label)} [{_attrs(attrs)}];")

    for ni in ghosts:
        attrs = {
            "label": ni.display_name, "shape": "ellipse",
            "style": "dashed,filled", "color": "gray70", "fillcolor": "gray95",
            "URL": ni.label, "tooltip": f"(external) {ni.label}",
        }
        lines.append(f"  {_q(ni.label)} [{_attrs(attrs)}];")

    for e in edges:
        if e.source not in visible or e.target not in visible:
            continue
        style = {"proof": "solid", "statement": "dashed",
                 "inferred": "dotted"}.get(e.location, "solid")
        attrs = {"style": style, "tooltip": f"{e.rule}: {e.source} -> {e.target}"}
        if e.key() in cycle_edges:
            attrs["color"] = "red"
        lines.append(f"  {_q(e.source)} -> {_q(e.target)} [{_attrs(attrs)}];")

    if add_legend and env_config:
        lines.append(f"  __legend__ [{_attrs(_legend_attrs(env_config))}];")

    lines.append("}")
    return "\n".join(lines) + "\n"


def _legend_attrs(env_config):
    rows = []
    for env_name in sorted(env_config.keys()):
        cfg = env_config[env_name]
        shape = cfg.get("shape", "ellipse")
        border = cfg.get("border", "black")
        fill = cfg.get("fill", "white")
        rows.append(
            f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">{env_name}</FONT></TD>'
            f'<TD ALIGN="LEFT"><FONT POINT-SIZE="9">{shape}</FONT></TD>'
            f'<TD BGCOLOR="{fill}" BORDER="1" COLOR="{border}">  </TD></TR>'
        )
    rows.append('<TR><TD COLSPAN="3"><FONT POINT-SIZE="6"> </FONT></TD></TR>')
    rows.append('<TR><TD ALIGN="LEFT" COLSPAN="3">'
                '<FONT POINT-SIZE="9">&#8212;&#8212; solid = from proof</FONT></TD></TR>')
    rows.append('<TR><TD ALIGN="LEFT" COLSPAN="3">'
                '<FONT POINT-SIZE="9">- - - dashed = from statement</FONT></TD></TR>')
    rows.append('<TR><TD ALIGN="LEFT" COLSPAN="3">'
                '<FONT POINT-SIZE="9">&#183;&#183;&#183;&#183; dotted = heuristic</FONT></TD></TR>')
    html = HtmlLabel('<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2">'
                     + "".join(rows) + "</TABLE>>")
    return {"label": html, "shape": "none", "margin": "0"}
