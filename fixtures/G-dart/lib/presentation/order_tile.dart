// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import 'package:flutter/widgets.dart';
import 'package:shop/domain/domain.dart' show Order;

class OrderTile extends StatelessWidget {
  const OrderTile({super.key, required this.order});

  final Order order;

  @override
  Widget build(BuildContext context) => Text('${order.id}: ${order.totalCents} ct');
}
