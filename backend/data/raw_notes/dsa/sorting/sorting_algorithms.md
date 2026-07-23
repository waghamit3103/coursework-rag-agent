# Sorting Algorithms

## Comparison-based sorts

All comparison-based sorting algorithms share a fundamental lower bound:
Omega(n log n) comparisons in the worst case. This follows from a decision-tree
argument — there are n! possible orderings of n elements, and a binary
decision tree with only comparisons as branches needs at least log2(n!) =
Omega(n log n) levels to distinguish all of them. Any algorithm that claims
better than O(n log n) in the worst case using only comparisons is either
wrong or is secretly using extra information about the input (like counting
sort does).

### Merge sort

Merge sort is a divide-and-conquer algorithm: split the array in half,
recursively sort each half, then merge the two sorted halves in linear time.
It's O(n log n) in the worst, best, and average case — very predictable —
and it's stable (equal elements keep their relative order), which matters
for sorting records by a secondary key after already sorting by a primary
key. The downside is O(n) auxiliary space for the merge step, unlike
quicksort or heapsort which can sort in place.

```python
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)
```

### Quicksort

Quicksort picks a pivot, partitions the array into elements less than and
greater than the pivot, then recursively sorts each partition. Average case
is O(n log n) with small constants (better cache locality than merge sort,
in-place partitioning), which is why it's often the fastest sort in
practice despite a worst case of O(n^2) — the worst case (already-sorted
input with a naive first-element pivot choice) is avoidable with randomized
or median-of-three pivot selection. Quicksort is not stable by default.

### Heapsort

Heapsort builds a max-heap from the array (O(n)), then repeatedly extracts
the maximum element and places it at the end (O(log n) per extraction,
n extractions, so O(n log n) total). It's in-place and has a guaranteed
O(n log n) worst case, unlike quicksort — but it has worse cache locality
than quicksort in practice (heap operations jump around the array rather
than accessing it sequentially), so it's usually slower despite the better
worst-case guarantee. It's also not stable.

## Non-comparison sorts

### Counting sort

If the input consists of integers in a known, small range [0, k), counting
sort can sort in O(n + k) time by counting occurrences of each value and
using those counts to compute each element's final position. This beats the
Omega(n log n) comparison lower bound because it isn't comparison-based at
all — it exploits the fact that the keys are small integers rather than
arbitrary comparable objects.

### Radix sort

Radix sort sorts integers (or fixed-length strings) digit by digit, from
least significant to most significant, using a stable sort (usually counting
sort) as a subroutine for each digit. For d-digit numbers, this gives
O(d * (n + k)) where k is the base — for a fixed number of digits, this is
effectively O(n).

## Choosing an algorithm

For a general-purpose "just sort this" call, use the language's built-in
sort — Python's Timsort (a hybrid of merge sort and insertion sort, tuned
for real-world data that often has existing runs of sorted elements) or
Java's dual-pivot quicksort for primitives / Timsort for objects. Implement
your own sort by hand mainly when: you have a specific constraint the
built-in doesn't satisfy (guaranteed worst-case bound → heapsort; strict
memory limit → in-place algorithm; keys are small integers → counting or
radix sort), or when the problem is explicitly asking you to demonstrate
understanding of the algorithm itself.
