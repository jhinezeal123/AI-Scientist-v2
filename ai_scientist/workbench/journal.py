"""Serialize original Node objects; restore relationships without mutating input."""
from copy import deepcopy

from ai_scientist.treesearch.journal import Journal, Node


def journal_snapshot(journal: Journal) -> dict:
    return {"nodes": [deepcopy(node.to_dict()) for node in journal.nodes]}


def restore_journal(snapshot: dict) -> Journal:
    records = deepcopy(snapshot["nodes"])
    journal = Journal()
    parents = {}
    for record in records:
        node_id = record["id"]
        if node_id in parents:
            raise ValueError("Duplicate journal node ID")
        parents[node_id] = record.get("parent_id")
        node = Node.from_dict(record)
        journal.append(node)
    for node in journal.nodes:
        parent_id = parents[node.id]
        if parent_id is not None:
            parent = journal.get_node_by_id(parent_id)
            if parent is None:
                raise ValueError("Journal parent is missing")
            seen = {node.id}
            ancestor = parent_id
            while ancestor is not None:
                if ancestor in seen:
                    raise ValueError("Journal parent cycle")
                seen.add(ancestor)
                ancestor = parents[ancestor]
            node.parent = parent
            parent.children.add(node)
    return journal
