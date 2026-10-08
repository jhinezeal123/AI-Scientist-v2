"""Original ParallelAgent branch selection, shared with remote executors."""
import random
from typing import List, Optional
from rich import print
from .journal import Node


def get_leaves(node: Node) -> List[Node]:
    """Get all leaf nodes in the subtree rooted at node."""
    if not node.children:
        return [node]

    leaves = []
    for child in node.children:
        leaves.extend(get_leaves(child))
    return leaves

def select_parallel_nodes(self) -> List[Optional[Node]]:
    """Select N nodes to process in parallel,
    balancing between tree exploration and exploitation.
    Note:
    - This function runs in the main process.
    Some design considerations:
    - For Stage 2 and 4, we generate nodes in the main process and
    send them to worker processes.
    This is to make sure we don't run duplicate ideas in parallel.
    - For Stage 1 and 3, we generate nodes in worker processes.
    """
    nodes_to_process = []
    processed_trees = set()
    search_cfg = self.cfg.agent.search
    print(f"[cyan]self.num_workers: {self.num_workers}, [/cyan]")

    while len(nodes_to_process) < self.num_workers:
        # Initial drafting phase, creating root nodes
        print(
            f"Checking draft nodes... num of journal.draft_nodes: {len(self.journal.draft_nodes)}, search_cfg.num_drafts: {search_cfg.num_drafts}"
        )
        if len(self.journal.draft_nodes) < search_cfg.num_drafts:
            nodes_to_process.append(None)
            continue

        # Get viable trees
        viable_trees = [
            root
            for root in self.journal.draft_nodes
            if not all(leaf.is_buggy for leaf in get_leaves(root))
        ]

        # Debugging phase (with some probability)
        if random.random() < search_cfg.debug_prob:
            print("Checking debuggable nodes")
            # print(f"Buggy nodes: {self.journal.buggy_nodes}")
            try:
                debuggable_nodes = None
                print("Checking buggy nodes...")
                buggy_nodes = self.journal.buggy_nodes
                print(f"Type of buggy_nodes: {type(buggy_nodes)}")
                print(f"Length of buggy_nodes: {len(buggy_nodes)}")

                for i, n in enumerate(buggy_nodes):
                    if not isinstance(n, Node):
                        print(f"Found non-Node object in journal.buggy_nodes: {n}")
                        raise ValueError(
                            "Found non-Node object in journal.buggy_nodes"
                        )
                debuggable_nodes = [
                    n
                    for n in self.journal.buggy_nodes
                    if (
                        isinstance(n, Node)
                        and n.is_leaf
                        and n.debug_depth <= search_cfg.max_debug_depth
                    )
                ]
            except Exception as e:
                print(f"Error getting debuggable nodes: {e}")
            if debuggable_nodes:
                print("Found debuggable nodes")
                node = random.choice(debuggable_nodes)
                tree_root = node
                while tree_root.parent:
                    tree_root = tree_root.parent

                tree_id = id(tree_root)
                if tree_id not in processed_trees or len(processed_trees) >= len(
                    viable_trees
                ):
                    nodes_to_process.append(node)
                    processed_trees.add(tree_id)
                    continue

        # Special handling for Stage 4 (Ablation Studies)
        print(f"[red]self.stage_name: {self.stage_name}[/red]")
        # print(f"[red]self.best_stage3_node: {self.best_stage3_node}[/red]")
        if self.stage_name and self.stage_name.startswith("4_"):
            nodes_to_process.append(self.best_stage3_node)
            continue
        # Special handling for Stage 2 (Hyperparam tuning for baseline)
        elif self.stage_name and self.stage_name.startswith("2_"):
            nodes_to_process.append(self.best_stage1_node)
            continue
        else:  # Stage 1, 3 (normal best-first search)
            # Improvement phase
            print("Checking good nodes..")
            good_nodes = self.journal.good_nodes
            if not good_nodes:
                nodes_to_process.append(None)  # Back to drafting
                continue

            # Get best node from unprocessed tree if possible
            best_node = self.journal.get_best_node(cfg=self.cfg)
            tree_root = best_node
            while tree_root.parent:
                tree_root = tree_root.parent

            tree_id = id(tree_root)
            if tree_id not in processed_trees or len(processed_trees) >= len(
                viable_trees
            ):
                nodes_to_process.append(best_node)
                processed_trees.add(tree_id)
                continue

            # If we can't use best node (tree already processed), try next best nodes
            for node in sorted(good_nodes, key=lambda n: n.metric, reverse=True):
                tree_root = node
                while tree_root.parent:
                    tree_root = tree_root.parent
                tree_id = id(tree_root)
                if tree_id not in processed_trees or len(processed_trees) >= len(
                    viable_trees
                ):
                    nodes_to_process.append(node)
                    processed_trees.add(tree_id)
                    break

    return nodes_to_process

