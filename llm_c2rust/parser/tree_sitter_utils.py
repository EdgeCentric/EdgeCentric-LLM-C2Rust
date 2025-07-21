from tree_sitter import Node


def has_error(node: Node) -> bool:
    if node.type == "ERROR":
        return True
    return any(has_error(child) for child in node.children)


def has_named_child(node: Node, name: str) -> bool:
    if node.child_by_field_name(name) is None:
        return False
    else:
        return True
