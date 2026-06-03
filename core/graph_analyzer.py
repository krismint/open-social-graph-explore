from __future__ import annotations

from pathlib import Path

import networkx as nx

from core.db import DEFAULT_DB_PATH, connect


def weighted_pagerank(graph: nx.DiGraph, alpha: float = 0.85, max_iter: int = 100, tol: float = 1.0e-6) -> dict[str, float]:
    nodes = list(graph.nodes)
    node_count = len(nodes)
    if node_count == 0:
        return {}

    rank = {node: 1.0 / node_count for node in nodes}
    out_weight = {
        node: sum(data.get("weight", 1.0) for _, _, data in graph.out_edges(node, data=True))
        for node in nodes
    }

    for _ in range(max_iter):
        previous = rank
        dangling_rank = sum(previous[node] for node in nodes if out_weight[node] == 0)
        rank = {node: (1.0 - alpha) / node_count + alpha * dangling_rank / node_count for node in nodes}

        for source in nodes:
            if out_weight[source] == 0:
                continue
            for _, target, data in graph.out_edges(source, data=True):
                rank[target] += alpha * previous[source] * data.get("weight", 1.0) / out_weight[source]

        error = sum(abs(rank[node] - previous[node]) for node in nodes)
        if error < node_count * tol:
            break

    return rank


def analyze_graph(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, int]:
    with connect(db_path) as conn:
        edges = conn.execute(
            """
            SELECT e.source_node, e.target_node, e.relation_type, e.weight
            FROM edges e
            JOIN accounts s ON s.account_id = e.source_node
            JOIN accounts t ON t.account_id = e.target_node
            WHERE e.weight > 0
              AND s.hidden_at IS NULL
              AND t.hidden_at IS NULL
            """
        ).fetchall()

        graph = nx.DiGraph()
        for edge in edges:
            source = edge["source_node"]
            target = edge["target_node"]
            weight = float(edge["weight"])
            if graph.has_edge(source, target):
                graph[source][target]["weight"] += weight
                graph[source][target]["relation_types"].append(edge["relation_type"])
            else:
                graph.add_edge(source, target, relation_types=[edge["relation_type"]], weight=weight)

        if graph.number_of_nodes() == 0:
            conn.execute("DELETE FROM node_scores")
            return {"nodes": 0, "db_edges": 0, "graph_edges": 0}

        degree = nx.degree_centrality(graph)
        betweenness = nx.betweenness_centrality(graph, weight="weight", normalized=True)
        pagerank = weighted_pagerank(graph)
        weighted_degree = {
            node: graph.degree(node, weight="weight")
            for node in graph.nodes
        }

        undirected = graph.to_undirected()
        communities = list(nx.algorithms.community.greedy_modularity_communities(undirected, weight="weight"))
        community_by_node = {}
        for index, community in enumerate(communities):
            for node in community:
                community_by_node[node] = index

        conn.execute("DELETE FROM node_scores")
        for node in graph.nodes:
            conn.execute(
                """
                INSERT INTO node_scores (
                    node_score_id, account_id, degree_centrality,
                    betweenness_centrality, pagerank, community_id,
                    weighted_degree, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    node,
                    node,
                    degree.get(node, 0.0),
                    betweenness.get(node, 0.0),
                    pagerank.get(node, 0.0),
                    community_by_node.get(node),
                    weighted_degree.get(node, 0.0),
                ),
            )

        return {"nodes": graph.number_of_nodes(), "db_edges": len(edges), "graph_edges": graph.number_of_edges()}
