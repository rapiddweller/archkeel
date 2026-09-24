// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

class OrderLine {
  const OrderLine(this.description, this.quantity, this.unitCents);

  final String description;
  final int quantity;
  final int unitCents;
}

class Order {
  const Order(this.id, this.lines);

  final String id;
  final List<OrderLine> lines;

  int get totalCents => lines.fold(0, (sum, line) => sum + line.quantity * line.unitCents);
}

/// A basket not yet placed. Only the domain turns it into an [Order], so the facade does not
/// export it.
class OrderDraft {
  final List<OrderLine> lines = [];

  Order place(String id) => Order(id, List.unmodifiable(lines));
}
