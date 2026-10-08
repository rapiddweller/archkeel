import 'package:flutter/material.dart';
import 'package:shop/domain/orders/order.dart';

class OrderDetailPage extends StatelessWidget {
  const OrderDetailPage(this.order);

  final Order order;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Order detail')),
    body: ListView(
      children: [
        for (final line in order.lines)
          ListTile(title: Text('${line.name} × ${line.quantity}')),
        ListTile(title: Text('Total ${_money(order.totalCents)}')),
      ],
    ),
  );
}

String _money(int cents) =>
    '\$${(cents ~/ 100)}.${(cents % 100).toString().padLeft(2, '0')}';
