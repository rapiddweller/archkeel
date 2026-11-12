// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The ranges that contain a range: `start <= query.start and query.end <= end`, the test of
//! `_sites`, `_scope_name` and `_callable_context_for`. Python tests each pair; the sweep gives
//! the same fold in O((n + m) log n), so a large source cannot make the work grow with n * m.

/// A sweep over items with a byte range and a value. The queries come in an order where the
/// start never decreases, which is the order of a walk of a Tree-sitter tree.
pub(crate) struct Sweep<T: Copy> {
    /// The items, sorted by start; the sort is stable.
    items: Vec<(usize, usize, T)>,
    /// The ends of the items, sorted and unique: the coordinates of the Fenwick tree.
    ends: Vec<usize>,
    /// The Fenwick tree from 1. Index `i` holds the items whose end has the rank `i` from the
    /// largest end, so a prefix holds the items whose end is at least a value.
    tree: Vec<T>,
    next: usize,
    last: usize,
    empty: T,
    join: fn(T, T) -> T,
}

impl<T: Copy> Sweep<T> {
    /// `join` must be associative and commutative, and `empty` its neutral value.
    pub(crate) fn new(mut items: Vec<(usize, usize, T)>, empty: T, join: fn(T, T) -> T) -> Self {
        items.sort_by_key(|item| item.0);
        let mut ends: Vec<usize> = items.iter().map(|item| item.1).collect();
        ends.sort_unstable();
        ends.dedup();
        let tree = vec![empty; ends.len().saturating_add(1)];
        Self {
            items,
            ends,
            tree,
            next: 0,
            last: 0,
            empty,
            join,
        }
    }

    /// The fold of the items that contain `start..end`, or `None` when `start` is lower than the
    /// start of the previous query: then the sweep cannot give the result.
    pub(crate) fn query(&mut self, start: usize, end: usize) -> Option<T> {
        if start < self.last {
            return None;
        }
        self.last = start;
        while let Some(&(item_start, item_end, value)) = self.items.get(self.next) {
            if item_start > start {
                break;
            }
            self.next = self.next.saturating_add(1);
            let rank = self
                .ends
                .len()
                .saturating_sub(self.ends.partition_point(|e| *e < item_end));
            self.add(rank, value);
        }
        let first = self.ends.partition_point(|e| *e < end);
        Some(self.prefix(self.ends.len().saturating_sub(first)))
    }

    fn add(&mut self, rank: usize, value: T) {
        let mut index = rank;
        while index > 0 {
            let Some(slot) = self.tree.get_mut(index) else {
                return;
            };
            *slot = (self.join)(*slot, value);
            index = index.saturating_add(index & index.wrapping_neg());
        }
    }

    fn prefix(&self, rank: usize) -> T {
        let mut result = self.empty;
        let mut index = rank;
        while let Some(value) = self.tree.get(index).filter(|_| index > 0) {
            result = (self.join)(result, *value);
            index &= index.wrapping_sub(1);
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::Sweep;

    fn count(a: usize, b: usize) -> usize {
        a.saturating_add(b)
    }

    /// The pairwise test of Python on each query.
    fn pairwise(items: &[(usize, usize, usize)], start: usize, end: usize) -> usize {
        items
            .iter()
            .filter(|(s, e, _)| *s <= start && end <= *e)
            .count()
    }

    #[test]
    fn the_sweep_counts_the_ranges_that_contain_each_query() {
        let items = vec![
            (0, 10, 1),
            (2, 8, 1),
            (2, 8, 1),
            (3, 3, 1),
            (5, 20, 1),
            (9, 9, 1),
        ];
        let mut sweep = Sweep::new(items.clone(), 0, count);
        for (start, end) in [
            (0, 0),
            (0, 10),
            (2, 8),
            (3, 3),
            (3, 4),
            (5, 9),
            (9, 9),
            (9, 10),
            (12, 30),
        ] {
            let found = sweep.query(start, end);
            assert_eq!(found, Some(pairwise(&items, start, end)), "{start}..{end}");
        }
    }

    #[test]
    fn a_query_with_a_lower_start_gives_no_result() {
        let mut sweep = Sweep::new(vec![(0, 10, 1)], 0, count);
        assert_eq!(sweep.query(5, 6), Some(1));
        assert_eq!(sweep.query(4, 6), None);
    }

    #[test]
    fn the_fold_keeps_the_best_item_with_a_total_order() {
        // `max` with the start and then the lowest index: the first maximum of Python `max`.
        let join = |a: Option<(usize, std::cmp::Reverse<usize>)>, b| a.max(b);
        let items = vec![
            (0, 9, Some((0, std::cmp::Reverse(0)))),
            (4, 9, Some((4, std::cmp::Reverse(1)))),
            (4, 9, Some((4, std::cmp::Reverse(2)))),
        ];
        let mut sweep = Sweep::new(items, None, join);
        assert_eq!(sweep.query(5, 6), Some(Some((4, std::cmp::Reverse(1)))));
    }
}
