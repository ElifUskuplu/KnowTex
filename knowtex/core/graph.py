"""Graphviz graph construction from nodes and dependency edges."""

import logging

try:
    from pygraphviz import AGraph
except ImportError:
    AGraph = None

logger = logging.getLogger("knowtex")


def build_graph(nodes, edges, env_config, section_assignments=None,
                filter_sections=None, filter_envs=None,
                view_mode="macro", micro_section=None,
                add_legend=True, cycle_edges=None):
    """Build Graphviz AGraph. Macro view is FLAT (no clusters).

    Parameters:
        nodes: list[NodeInfo]
        edges: list[DependencyEdge]
        env_config: {env_name -> {"shape", "border", "fill"}}
        section_assignments: {label -> section_title} (optional)
        filter_sections: set of section titles to include (optional)
        filter_envs: set of env names to include (optional)
        view_mode: "macro" or "micro"
        micro_section: section title for micro view
        add_legend: whether to add legend node
        cycle_edges: set of (source, target) keys for cycle edges
    """
    if AGraph is None:
        raise ImportError("pygraphviz is required for graph building.")

    G = AGraph(directed=True, bgcolor="transparent", strict=False)
    G.node_attr["penwidth"] = 1.8
    G.edge_attr.update(arrowhead="vee")

    if section_assignments is None:
        section_assignments = {}
    if cycle_edges is None:
        cycle_edges = set()

    # Determine which nodes to include
    included_labels = set()
    ghost_labels = set()

    for ni in nodes:
        if ni.env not in env_config:
            continue
        if filter_envs is not None and ni.env not in filter_envs:
            continue
        sec = section_assignments.get(ni.label, "(ungrouped)")
        if filter_sections and sec not in filter_sections:
            continue
        if view_mode == "micro" and micro_section:
            if sec == micro_section:
                included_labels.add(ni.label)
        else:
            included_labels.add(ni.label)

    # Micro view: find ghost nodes (outside section but connected)
    if view_mode == "micro" and micro_section:
        for e in edges:
            if e.source in included_labels and e.target not in included_labels:
                ghost_labels.add(e.target)
            if e.target in included_labels and e.source not in included_labels:
                ghost_labels.add(e.source)

    label_to_ni = {ni.label: ni for ni in nodes}

    # Add included nodes
    for ni in nodes:
        if ni.label not in included_labels:
            continue
        cfg = env_config.get(ni.env, {})
        G.add_node(
            ni.label,
            label=ni.display_name,
            shape=cfg.get("shape", "ellipse"),
            style="filled",
            color=cfg.get("border", "black"),
            fillcolor=cfg.get("fill", "white"),
            URL=ni.label,
            tooltip=ni.label,
        )

    # Add ghost nodes (micro view)
    for lbl in ghost_labels:
        ni = label_to_ni.get(lbl)
        if ni:
            G.add_node(
                lbl,
                label=ni.display_name,
                shape="ellipse",
                style="dashed,filled",
                color="gray70",
                fillcolor="gray95",
                URL=lbl,
                tooltip=f"(external) {lbl}",
            )

    all_visible = included_labels | ghost_labels

    # Add edges with style based on location
    for e in edges:
        if e.source in all_visible and e.target in all_visible:
            attrs = {}

            # Edge style based on location
            if e.location == "proof":
                attrs["style"] = "solid"
            elif e.location == "statement":
                attrs["style"] = "dashed"
            elif e.location == "inferred":
                attrs["style"] = "dotted"
            else:
                attrs["style"] = "solid"

            # Cycle edge highlighting
            if e.key() in cycle_edges:
                attrs["color"] = "red"

            G.add_edge(e.source, e.target, **attrs)

    # Add legend
    if add_legend and env_config:
        _add_legend(G, env_config)

    return G


def _add_legend(G, env_config):
    """Add a legend box showing environment -> shape/color mapping."""
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

    # Edge style legend
    rows.append(
        '<TR><TD COLSPAN="3"><FONT POINT-SIZE="6"> </FONT></TD></TR>'
    )
    rows.append(
        '<TR><TD ALIGN="LEFT" COLSPAN="3">'
        '<FONT POINT-SIZE="9">&#8212;&#8212; solid = from proof</FONT></TD></TR>'
    )
    rows.append(
        '<TR><TD ALIGN="LEFT" COLSPAN="3">'
        '<FONT POINT-SIZE="9">- - - dashed = from statement</FONT></TD></TR>'
    )
    rows.append(
        '<TR><TD ALIGN="LEFT" COLSPAN="3">'
        '<FONT POINT-SIZE="9">&#183;&#183;&#183;&#183; dotted = heuristic</FONT></TD></TR>'
    )

    html_label = (
        f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2">'
        f'{"".join(rows)}</TABLE>>'
    )

    G.add_node(
        "__legend__",
        label=html_label,
        shape="none",
        margin="0",
    )
