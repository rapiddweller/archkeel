import 'package:flutter/material.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/presentation/orders/orders_view_model.dart';
import 'package:shop/state/async_state.dart';

class OrdersPage extends StatelessWidget {
  const OrdersPage(this.viewModel);

  final OrdersViewModel viewModel;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Orders')),
    body: ListenableBuilder(
      listenable: viewModel,
      builder: (context, _) => switch (viewModel.state.phase) {
        LoadPhase.idle ||
        LoadPhase.loading => const Center(child: Text('Loading orders…')),
        LoadPhase.failed => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load orders'),
              TextButton(onPressed: viewModel.load, child: const Text('Retry')),
            ],
          ),
        ),
        LoadPhase.empty => const Center(child: Text('No orders yet')),
        LoadPhase.ready => ListView(
          children: [
            for (final order in viewModel.state.value ?? const <Order>[])
              ListTile(
                key: ValueKey(order.id),
                title: Text('Order #${order.id.split('-').last}'),
                subtitle: Text(
                  '${order.status.label} · ${_money(order.totalCents)}',
                ),
                onTap: () async {
                  final selected = await viewModel.findById(order.id);
                  if (!context.mounted || selected == null) return;
                  await Navigator.of(
                    context,
                  ).pushNamed('/order', arguments: selected);
                },
              ),
          ],
        ),
      },
    ),
  );
}

String _money(int cents) =>
    '\$${(cents ~/ 100)}.${(cents % 100).toString().padLeft(2, '0')}';
