# Binary Search Trees

A binary search tree (BST) is a binary tree where each node's left subtree
contains only values less than the node's value, and the right subtree only
values greater than it.

## Insertion

To insert a value, walk down from the root, going left or right depending on
the comparison with the current node, until you reach a null pointer, then
attach the new node there.

## Traversal

### In-order

Visit the left subtree, then the node itself, then the right subtree. This
produces sorted output for a valid BST.

```python
def inorder(node):
    if node:  # a stray '#' in a comment should not be a heading
        inorder(node.left)
        print(node.value)
        inorder(node.right)
```

### Pre-order

Visit the node, then the left subtree, then the right subtree. Useful for
producing a copy of the tree structure.

# Heaps

A heap is a complete binary tree satisfying the heap property: every parent
node is ordered with respect to its children (min-heap or max-heap).
