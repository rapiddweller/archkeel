import 'package:flutter/material.dart';
import 'package:shop/presentation/shopping/cart/cart_view_model.dart';
import 'package:shop/state/async_state.dart';

class CartPage extends StatelessWidget {
  const CartPage(this.viewModel);

  final CartViewModel viewModel;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Cart'),
      actions: [
        IconButton(
          key: const ValueKey('open-orders'),
          tooltip: 'Orders',
          onPressed: () => Navigator.of(context).pushNamed('/orders'),
          icon: const Icon(Icons.receipt_long),
        ),
      ],
    ),
    body: ListenableBuilder(
      listenable: viewModel,
      builder: (context, _) => Column(
        children: [
          Expanded(
            child: viewModel.lines.isEmpty
                ? const Center(child: Text('Your cart is empty'))
                : ListView(
                    children: [
                      for (final line in viewModel.lines)
                        ListTile(
                          title: Text(
                            '${line.product.name} × ${line.quantity}',
                          ),
                          subtitle: Text(_money(line.lineTotalCents)),
                          trailing: IconButton(
                            key: ValueKey('increase-${line.product.id}'),
                            tooltip: 'Add one ${line.product.name}',
                            onPressed: viewModel.isPlacingOrder
                                ? null
                                : () => viewModel.setQuantity(
                                    line.product.id,
                                    line.quantity + 1,
                                  ),
                            icon: const Icon(Icons.add),
                          ),
                        ),
                    ],
                  ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text('Total ${_money(viewModel.totalCents)}'),
                if (viewModel.state.phase == LoadPhase.failed)
                  const Text(
                    'Checkout failed. Check your connection and try again.',
                  ),
                if (viewModel.state.phase == LoadPhase.ready)
                  const Text('Order placed'),
                FilledButton(
                  key: const ValueKey('place-order'),
                  onPressed: viewModel.isPlacingOrder || viewModel.lines.isEmpty
                      ? null
                      : viewModel.checkout,
                  child: Text(
                    viewModel.isPlacingOrder ? 'Placing order…' : 'Place order',
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

String _money(int cents) =>
    '\$${(cents ~/ 100)}.${(cents % 100).toString().padLeft(2, '0')}';
