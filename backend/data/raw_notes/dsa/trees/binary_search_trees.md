# Binary Search Trees

A binary search tree (BST) is a binary tree where every node satisfies the
BST invariant: for any node `n`, every value in `n`'s left subtree is less
than `n`'s value, and every value in `n`'s right subtree is greater. This
invariant is what makes search, insertion, and deletion all achievable in
O(h) time, where h is the height of the tree.

In the best case (a balanced tree), h = O(log n), giving O(log n) operations.
In the worst case (a degenerate tree that's really just a linked list — for
example, inserting values in already-sorted order), h = O(n), and every
operation degrades to O(n). This is the core motivation for self-balancing
trees like AVL trees and red-black trees, covered later in the course.

## Insertion

To insert a value `v`:

1. Start at the root.
2. If the tree is empty, `v` becomes the root.
3. Otherwise, compare `v` to the current node. If `v` is less, recurse into
   the left subtree; if greater, recurse into the right subtree.
4. When you reach a null pointer, attach a new node containing `v` there.

Insertion is O(h) — the same bound as search, since insertion is really just
"search for where this value would be, then place it there."

```python
def insert(root, value):
    if root is None:
        return Node(value)
    if value < root.value:
        root.left = insert(root.left, value)
    elif value > root.value:
        root.right = insert(root.right, value)
    # duplicate values are ignored in this implementation
    return root
```

## Deletion

Deletion has three cases, and it's the case analysis — not the traversal —
that makes it the trickiest BST operation to implement correctly.

1. **Leaf node** (no children): just remove it.
2. **One child**: splice the node out, connecting its parent directly to its
   single child.
3. **Two children**: find the node's in-order successor (the smallest value
   in the right subtree — i.e., keep going left from `node.right` until you
   can't anymore), copy that successor's value into the node being deleted,
   then delete the successor node itself (which is guaranteed to have at
   most one child, so it recurses into an easier case).

Using the in-order *predecessor* (largest value in the left subtree) instead
of the successor works equally well — it's a symmetric choice, not a
correctness requirement.

## Traversal

### In-order

Visit left subtree, then the node, then right subtree. For a BST, in-order
traversal visits nodes in sorted order — this is the traversal to use when
you need sorted output.

```python
def inorder(node):
    if node:
        inorder(node.left)
        print(node.value)
        inorder(node.right)
```

### Pre-order

Visit the node, then left subtree, then right subtree. Useful for producing
a copy of the tree, or for serializing a tree structure such that it can be
deserialized by re-inserting values in the same order.

### Post-order

Visit left subtree, then right subtree, then the node. Useful when you need
to process children before their parent — for example, safely deleting an
entire tree bottom-up, or computing a value (like subtree height) that
depends on both children already being computed.

## Why balance matters

An unbalanced BST gives no better worst-case guarantee than a sorted linked
list. AVL trees maintain a strict balance factor (height difference between
left and right subtrees is at most 1 for every node) via rotations after
each insertion or deletion, guaranteeing O(log n) height at all times.
Red-black trees relax that balance condition slightly in exchange for fewer
rotations per update, which is why most standard library ordered map/set
implementations (including C++'s `std::map` and Java's `TreeMap`) use
red-black trees rather than AVL trees — fewer rotations means better
amortized performance for insert-heavy workloads, at the cost of a slightly
taller tree than a strict AVL tree would produce.
