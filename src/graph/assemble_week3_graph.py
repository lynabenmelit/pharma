"""Merge, validate, load, and visualize the Week 3 P2-P4 knowledge graph."""

import csv
import math
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

from src.graph.check_triples import REQUIRED_COLUMNS, validate_triples


ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = ROOT / "data" / "graph"
REPORT_DIR = ROOT / "reports"
TRIPLE_SOURCES = (
    ("P2 nomenclature", GRAPH_DIR / "triples_p2.csv"),
    ("P3 ANSM interactions", GRAPH_DIR / "triples_p3.csv"),
    ("P4 ANPP contraindications", GRAPH_DIR / "triples_p4.csv"),
)
BASE_VOCABULARY = GRAPH_DIR / "vocab.csv"
P4_ADDITIONS = GRAPH_DIR / "vocab_p4_additions.csv"
MERGED_TRIPLES = GRAPH_DIR / "triples_merged.csv"
MERGED_VOCABULARY = GRAPH_DIR / "vocab_merged.csv"
GRAPHML_OUTPUT = GRAPH_DIR / "pharma_knowledge_graph.graphml"
IMAGE_OUTPUT = REPORT_DIR / "week3_ten_medicines_graph.png"
REPORT_OUTPUT = REPORT_DIR / "week3_graph_report.md"

FOCUS_MEDICINES = {
    "diclofenac": "active_ingredient_diclofenac",
    "perindopril": "active_ingredient_perindopril",
    "ibuprofen": "active_ingredient_ibuprofene",
    "ramipril": "active_ingredient_ramipril",
    "amoxicillin": "active_ingredient_amoxicilline",
    "losartan": "active_ingredient_losartan",
    "naproxen": "active_ingredient_naproxene",
    "spironolactone": "active_ingredient_spironolactone",
    "enalapril": "active_ingredient_enalapril",
    "tramadol": "active_ingredient_tramadol",
}

NODE_COLORS = {
    "active_ingredient": "#2563eb",
    "medicament": "#16a34a",
    "therapeutic_class": "#f59e0b",
    "atc_code": "#8b5cf6",
    "literal": "#94a3b8",
    "indication": "#14b8a6",
    "adverse_effect": "#ef4444",
    "contraindication": "#dc2626",
}
EDGE_COLORS = {
    "brand_of": "#16a34a",
    "has_atc": "#8b5cf6",
    "belongs_to": "#f59e0b",
    "has_strength": "#64748b",
    "has_form": "#94a3b8",
    "interacts_with:CI": "#dc2626",
    "interacts_with:AD": "#ea580c",
    "interacts_with:PE": "#ca8a04",
    "interacts_with:APEC": "#0284c7",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        return list(reader)


def merge_vocabulary() -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    rows = read_csv(BASE_VOCABULARY)
    if not rows:
        raise ValueError(f"{BASE_VOCABULARY} contains no vocabulary rows")
    fieldnames = list(rows[0])
    entities = {
        row["name"]: row
        for row in rows
        if row.get("kind") == "entity"
    }

    additions = read_csv(P4_ADDITIONS)
    for row in additions:
        if row.get("kind") != "entity":
            raise ValueError(
                f"Unexpected non-entity P4 vocabulary addition: {row.get('name')}"
            )
        current = entities.get(row["name"])
        if current:
            if current.get("domain") != row.get("domain"):
                raise ValueError(
                    f"Conflicting vocabulary type for entity {row['name']}"
                )
            continue
        rows.append({column: row.get(column, "") for column in fieldnames})
        entities[row["name"]] = row

    with MERGED_VOCABULARY.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows, entities


def merge_triples() -> tuple[list[dict[str, str]], dict[str, int], int]:
    merged = []
    counts = {}
    seen = set()
    duplicates = 0
    for label, path in TRIPLE_SOURCES:
        source_rows = read_csv(path)
        counts[label] = len(source_rows)
        for row in source_rows:
            if tuple(row.get(column, "") for column in REQUIRED_COLUMNS) in seen:
                duplicates += 1
                continue
            seen.add(tuple(row.get(column, "") for column in REQUIRED_COLUMNS))
            merged.append({column: row.get(column, "") for column in REQUIRED_COLUMNS})

    with MERGED_TRIPLES.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(merged)
    return merged, counts, duplicates


def graph_node_id(value: str, entity_type: str) -> str:
    return f"literal::{value}" if entity_type == "literal" else value


def load_graph(
    triples: list[dict[str, str]],
    entities: dict[str, dict[str, str]],
) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for row in triples:
        for value_column, type_column in (
            ("subject", "subject_type"),
            ("object", "object_type"),
        ):
            value = row[value_column]
            entity_type = row[type_column]
            node_id = graph_node_id(value, entity_type)
            label = (
                entities.get(value, {}).get("description", "")
                if entity_type != "literal"
                else value
            )
            graph.add_node(
                node_id,
                entity_type=entity_type,
                label=label or value,
                value=value,
            )
        graph.add_edge(
            graph_node_id(row["subject"], row["subject_type"]),
            graph_node_id(row["object"], row["object_type"]),
            **{column: row[column] for column in REQUIRED_COLUMNS[2:]},
        )
    nx.write_graphml(graph, GRAPHML_OUTPUT)
    return graph


def focus_graph(
    triples: list[dict[str, str]],
    entities: dict[str, dict[str, str]],
) -> tuple[nx.MultiDiGraph, set[str]]:
    focus_ids = set(FOCUS_MEDICINES.values())
    available = {
        row["subject"]
        for row in triples
        if row["subject_type"] == "active_ingredient"
    }
    missing = focus_ids - available
    if missing:
        raise ValueError(
            "Focus medicines are missing from the graph: "
            + ", ".join(sorted(missing))
        )

    selected_nodes = set(focus_ids)
    for row in triples:
        if row["relation"] in {"has_form", "has_strength"}:
            continue
        if row["subject"] in focus_ids:
            selected_nodes.add(graph_node_id(row["object"], row["object_type"]))
        if row["object"] in focus_ids:
            selected_nodes.add(graph_node_id(row["subject"], row["subject_type"]))

    graph = nx.MultiDiGraph()
    focus_node_ids = {graph_node_id(value, "active_ingredient") for value in focus_ids}
    for row in triples:
        if row["relation"] in {"has_form", "has_strength"}:
            continue
        subject_id = graph_node_id(row["subject"], row["subject_type"])
        object_id = graph_node_id(row["object"], row["object_type"])
        is_focus_fact = (
            row["subject"] in focus_ids
            or row["object"] in focus_ids
            or (
                row["relation"].startswith("interacts_with:")
                and (subject_id in selected_nodes or object_id in selected_nodes)
            )
        )
        if not is_focus_fact:
            continue
        for node_id, value, entity_type in (
            (subject_id, row["subject"], row["subject_type"]),
            (object_id, row["object"], row["object_type"]),
        ):
            label = (
                entities.get(value, {}).get("description", value)
                if entity_type != "literal"
                else value
            )
            graph.add_node(
                node_id,
                entity_type=entity_type,
                label=label,
                is_focus=node_id in focus_node_ids,
            )
        graph.add_edge(
            subject_id,
            object_id,
            relation=row["relation"],
        )
    return graph, focus_node_ids


def focus_layout(graph: nx.MultiDiGraph, focus_node_ids: set[str]):
    core_nodes = sorted(focus_node_ids)
    positions = {}
    radius = 10
    for index, node in enumerate(core_nodes):
        angle = 2 * math.pi * index / len(core_nodes) - math.pi / 2
        positions[node] = (radius * math.cos(angle), radius * math.sin(angle))

    undirected = nx.Graph(graph)
    shared = []
    for core in core_nodes:
        neighbors = [
            node
            for node in undirected.neighbors(core)
            if node not in focus_node_ids
        ]
        neighbors.sort(
            key=lambda node: (
                graph.nodes[node]["entity_type"],
                graph.nodes[node]["label"].casefold(),
            )
        )
        for index, node in enumerate(neighbors):
            parents = [
                parent
                for parent in undirected.neighbors(node)
                if parent in focus_node_ids
            ]
            if len(parents) > 1:
                if node not in shared:
                    shared.append(node)
                continue
            if node in positions:
                continue
            angle = 2 * math.pi * (index + 1) / (len(neighbors) + 1)
            center_x, center_y = positions[core]
            positions[node] = (
                center_x + 2.2 * math.cos(angle),
                center_y + 2.2 * math.sin(angle),
            )

    for index, node in enumerate(shared):
        parents = [
            parent
            for parent in undirected.neighbors(node)
            if parent in focus_node_ids
        ]
        center_x = sum(positions[parent][0] for parent in parents) / len(parents)
        center_y = sum(positions[parent][1] for parent in parents) / len(parents)
        angle = 2 * math.pi * index / max(len(shared), 1)
        positions[node] = (
            center_x + 1.2 * math.cos(angle),
            center_y + 1.2 * math.sin(angle),
        )

    for node in graph:
        if node in positions:
            continue
        neighbors = [neighbor for neighbor in undirected.neighbors(node) if neighbor in positions]
        if not neighbors:
            continue
        center_x = sum(positions[item][0] for item in neighbors) / len(neighbors)
        center_y = sum(positions[item][1] for item in neighbors) / len(neighbors)
        positions[node] = (center_x + 1.8, center_y + 1.8)
    return positions


def draw_focus_graph(graph: nx.MultiDiGraph, focus_node_ids: set[str]) -> None:
    positions = focus_layout(graph, focus_node_ids)
    figure, axis = plt.subplots(figsize=(22, 16))
    axis.set_title(
        "Week 3 knowledge graph: 10 focus medicines and their recorded links",
        fontsize=20,
        pad=24,
    )

    for entity_type, color in NODE_COLORS.items():
        nodes = [
            node
            for node, attributes in graph.nodes(data=True)
            if attributes.get("entity_type") == entity_type
        ]
        if nodes:
            nx.draw_networkx_nodes(
                graph,
                positions,
                nodelist=nodes,
                node_color=color,
                node_size=[
                    1100 if node in focus_node_ids else 600
                    for node in nodes
                ],
                edgecolors="#1f2937",
                linewidths=0.8,
                ax=axis,
            )

    for relation, color in EDGE_COLORS.items():
        edges = [
            (source, target, key)
            for source, target, key, attributes in graph.edges(
                keys=True,
                data=True,
            )
            if attributes.get("relation") == relation
        ]
        if edges:
            nx.draw_networkx_edges(
                graph,
                positions,
                edgelist=edges,
                edge_color=color,
                arrows=True,
                arrowsize=13,
                width=1.5,
                connectionstyle="arc3,rad=0.06",
                ax=axis,
            )

    labels = {
        node: textwrap.fill(attributes["label"], width=17)
        for node, attributes in graph.nodes(data=True)
    }
    nx.draw_networkx_labels(
        graph,
        positions,
        labels=labels,
        font_size=7,
        font_weight="bold",
        ax=axis,
    )

    node_handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label=entity_type.replace("_", " "),
            markerfacecolor=color,
            markeredgecolor="#1f2937",
            markersize=9,
        )
        for entity_type, color in NODE_COLORS.items()
        if any(
            attributes.get("entity_type") == entity_type
            for _, attributes in graph.nodes(data=True)
        )
    ]
    node_legend = axis.legend(
        handles=node_handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        title="Node type",
        frameon=False,
    )
    axis.add_artist(node_legend)
    graph_relations = {
        attributes["relation"]
        for _, _, attributes in graph.edges(data=True)
    }
    relation_handles = [
        plt.Line2D(
            [0],
            [0],
            color=EDGE_COLORS[relation],
            label=relation,
            linewidth=2,
        )
        for relation in EDGE_COLORS
        if relation in graph_relations
    ]
    axis.legend(
        handles=relation_handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 0.62),
        title="Relations",
        frameon=False,
    )
    axis.text(
        0.01,
        0.01,
        "Arrows show relation direction. Interactions are included only when "
        "their existing class/ingredient endpoints connect to a focus node; "
        "no unstated medicine-class links are inferred.",
        transform=axis.transAxes,
        fontsize=9,
        va="bottom",
        wrap=True,
    )
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(IMAGE_OUTPUT, dpi=180, bbox_inches="tight")
    plt.close(figure)


def write_report(
    triples: list[dict[str, str]],
    source_counts: dict[str, int],
    duplicate_count: int,
    graph: nx.MultiDiGraph,
    focus: nx.MultiDiGraph,
    focus_node_ids: set[str],
    validation_errors: list[str],
) -> None:
    type_counts = {}
    for _, attributes in graph.nodes(data=True):
        entity_type = attributes["entity_type"]
        type_counts[entity_type] = type_counts.get(entity_type, 0) + 1

    p4_products = {
        row["subject"]
        for row in triples
        if row["relation"] == "contraindicated_in"
    }
    report_lines = [
        "# Week 3 Knowledge Graph: P5 Assembly and Evaluation",
        "",
        "## Scope",
        "",
        "Merged P2 nomenclature, P3 ANSM interaction, and P4 ANPP "
        "contraindication triples. The older `triples_step3.csv` extraction "
        "was excluded because it is a separate, unverified dataset.",
        "",
        "## Merge and validation",
        "",
        "| Input | Triples |",
        "|---|---:|",
    ]
    report_lines.extend(
        f"| {label} (`{path.name}`) | {source_counts[label]} |"
        for label, path in TRIPLE_SOURCES
    )
    report_lines.extend(
        [
            f"| Exact duplicate rows removed | {duplicate_count} |",
            f"| **Merged triples** | **{len(triples)}** |",
            "",
            f"The merged graph contains **{graph.number_of_nodes()} nodes** and "
            f"**{graph.number_of_edges()} directed edges**. Validation "
            f"{'passed' if not validation_errors else 'failed'} with "
            f"{len(validation_errors)} error(s).",
            "",
            "### Nodes by type",
            "",
            "| Type | Count |",
            "|---|---:|",
        ]
    )
    report_lines.extend(
        f"| {entity_type} | {count} |"
        for entity_type, count in sorted(type_counts.items())
    )
    report_lines.extend(
        [
            "",
            "## Ten-medicine visualization",
            "",
            f"All **{len(focus_node_ids)} of 10** requested active ingredients "
            f"are present. The focused drawing contains "
            f"{focus.number_of_nodes()} nodes and {focus.number_of_edges()} "
            "recorded relations, including directly connected brands, "
            "classes, ATC codes, and relevant P3 interaction edges. Dosage "
            "forms and strengths remain available in the full GraphML/CSV "
            "but are omitted from this drawing to keep it readable.",
            "",
            f"![Focused graph of the 10 medicines](week3_ten_medicines_graph.png)",
            "",
            "## Integration caveat",
            "",
            f"P4 contributes **{len(p4_products)} product-specific "
            "contraindication subjects** to the full merged graph. These "
            "RCP product/form nodes are not relabeled or falsely connected to "
            "the 10 ingredient-level P2 medicines. The P4 facts remain in the "
            "merged graph but outside the focused 10-medicine drawing unless "
            "a source-backed product-to-ingredient edge is added.",
            "",
            "## Outputs",
            "",
            "- `data/graph/triples_merged.csv` — merged P2-P4 triples.",
            "- `data/graph/vocab_merged.csv` — current base vocabulary plus P4 entities.",
            "- `data/graph/pharma_knowledge_graph.graphml` — loaded directed multigraph.",
            "- `reports/week3_ten_medicines_graph.png` — focused drawing.",
            "- `reports/week3_graph_report.md` — this summary.",
        ]
    )
    REPORT_OUTPUT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _, entities = merge_vocabulary()
    triples, source_counts, duplicate_count = merge_triples()
    errors, _ = validate_triples(MERGED_TRIPLES, MERGED_VOCABULARY)
    if errors:
        raise ValueError("Merged graph validation failed:\n" + "\n".join(errors))

    graph = load_graph(triples, entities)
    focus, focus_node_ids = focus_graph(triples, entities)
    draw_focus_graph(focus, focus_node_ids)
    write_report(
        triples,
        source_counts,
        duplicate_count,
        graph,
        focus,
        focus_node_ids,
        errors,
    )
    print(
        f"Merged {len(triples)} triples; loaded {graph.number_of_nodes()} nodes "
        f"and {graph.number_of_edges()} edges. All 10 focus medicines found. "
        f"Graph validation passed. Report: {REPORT_OUTPUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
