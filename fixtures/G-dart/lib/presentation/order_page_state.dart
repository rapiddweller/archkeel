// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

part of 'order_page.dart';

class _OrderPageState extends State<OrderPage> {
  List<Order> _orders = const [];

  @override
  void initState() {
    super.initState();
    widget.repository.ordersOf('demo').then((orders) => setState(() => _orders = orders));
  }

  @override
  Widget build(BuildContext context) => ListView(
        children: [for (final order in _orders) OrderTile(order: order)],
      );
}
