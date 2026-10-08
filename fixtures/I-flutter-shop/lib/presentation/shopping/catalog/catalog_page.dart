import 'package:flutter/material.dart';
import 'package:shop/domain/catalog/product.dart';
import 'package:shop/presentation/orders/orders_view_model.dart';
import 'package:shop/presentation/shopping/cart/cart_view_model.dart';
import 'package:shop/presentation/shopping/catalog/catalog_view_model.dart';
import 'package:shop/state/async_state.dart';

class CatalogPage extends StatelessWidget {
  const CatalogPage(this.catalog, this.cart, this.orders);

  final CatalogViewModel catalog;
  final CartViewModel cart;
  final OrdersViewModel orders;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Shop'),
      actions: [
        IconButton(
          key: const ValueKey('open-orders'),
          tooltip: 'Orders',
          onPressed: () => Navigator.of(context).pushNamed('/orders'),
          icon: const Icon(Icons.receipt_long),
        ),
        IconButton(
          key: const ValueKey('open-cart'),
          tooltip: 'Cart',
          onPressed: () => Navigator.of(context).pushNamed('/cart'),
          icon: const Icon(Icons.shopping_cart),
        ),
      ],
    ),
    body: ListenableBuilder(
      listenable: catalog,
      builder: (context, _) => Column(
        children: [
          SwitchListTile(
            key: const ValueKey('toggle-online'),
            title: Text(
              catalog.isOnline ? 'Online' : 'Offline: cached catalog',
            ),
            value: catalog.isOnline,
            onChanged: catalog.setOnline,
          ),
          Expanded(child: _catalogBody(context, catalog.state)),
        ],
      ),
    ),
  );

  Widget _catalogBody(BuildContext context, AsyncState<List<Product>> state) =>
      switch (state.phase) {
        LoadPhase.idle ||
        LoadPhase.loading => const Center(child: Text('Loading catalog…')),
        LoadPhase.failed => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load catalog'),
              TextButton(
                key: const ValueKey('retry-catalog'),
                onPressed: catalog.retry,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        LoadPhase.empty => const Center(child: Text('No products available')),
        LoadPhase.ready => ListView(
          children: [
            for (final product in state.value ?? const <Product>[])
              ListTile(
                title: Text(product.name),
                subtitle: Text(_money(product.priceCents)),
                trailing: IconButton(
                  key: ValueKey('add-${product.id}'),
                  tooltip: 'Add ${product.name}',
                  onPressed: cart.isPlacingOrder
                      ? null
                      : () => cart.addProduct(product),
                  icon: const Icon(Icons.add_shopping_cart),
                ),
              ),
          ],
        ),
      };
}

String _money(int cents) =>
    '\$${(cents ~/ 100)}.${(cents % 100).toString().padLeft(2, '0')}';
