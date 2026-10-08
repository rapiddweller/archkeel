import 'package:flutter/material.dart';
import 'package:shop/data/services/demo_backend.dart';
import 'package:shop/data/services/memory_store.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/presentation/orders/order_detail_page.dart';
import 'package:shop/presentation/orders/orders_page.dart';
import 'package:shop/presentation/orders/orders_view_model.dart';
import 'package:shop/presentation/shopping/cart/cart_page.dart';
import 'package:shop/presentation/shopping/cart/cart_view_model.dart';
import 'package:shop/presentation/shopping/catalog/catalog_page.dart';
import 'package:shop/presentation/shopping/catalog/catalog_view_model.dart';

class ShopApp extends StatefulWidget {
  const ShopApp(
    DemoBackend backend,
    MemoryStore store,
    CatalogViewModel catalog,
    CartViewModel cart,
    OrdersViewModel orders,
  ) : _backend = backend,
      _store = store,
      _catalog = catalog,
      _cart = cart,
      _orders = orders;

  final DemoBackend _backend;
  final MemoryStore _store;
  final CatalogViewModel _catalog;
  final CartViewModel _cart;
  final OrdersViewModel _orders;

  @override
  State<ShopApp> createState() => _ShopAppState();
}

class _ShopAppState extends State<ShopApp> {
  @override
  Widget build(BuildContext context) {
    assert(widget._backend.isOnline() == widget._catalog.isOnline);
    return MaterialApp(
      title: 'Flutter Shop',
      initialRoute: '/',
      onGenerateRoute: (settings) {
        return switch ((settings.name, settings.arguments)) {
          ('/', _) => MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => CatalogPage(widget._catalog, widget._cart),
          ),
          ('/cart', _) => MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => CartPage(widget._cart),
          ),
          ('/orders', _) => MaterialPageRoute<void>(
            settings: settings,
            builder: (_) =>
                OrdersPage(widget._orders, widget._catalog.isOnline),
          ),
          ('/order', final Order order) => MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => OrderDetailPage(order),
          ),
          _ => MaterialPageRoute<void>(
            builder: (_) =>
                const Scaffold(body: Center(child: Text('Page not found'))),
          ),
        };
      },
    );
  }

  @override
  void dispose() {
    widget._catalog.dispose();
    widget._cart.dispose();
    widget._orders.dispose();
    widget._store.dispose();
    super.dispose();
  }
}
