import 'package:flutter/material.dart';
import 'package:shop/app/shop_app.dart';
import 'package:shop/data/repositories/cached_catalog_repository.dart';
import 'package:shop/data/repositories/memory_order_repository.dart';
import 'package:shop/data/services/demo_backend.dart';
import 'package:shop/data/services/memory_store.dart';
import 'package:shop/domain/checkout/place_order.dart';
import 'package:shop/presentation/orders/orders_view_model.dart';
import 'package:shop/presentation/shopping/cart/cart_view_model.dart';
import 'package:shop/presentation/shopping/catalog/catalog_view_model.dart';

const APP_VERSION = '0.1.0';

void main() {
  final backend = DemoBackend();
  final store = MemoryStore();
  final catalogRepository = CachedCatalogRepository(backend, store);
  final orderRepository = MemoryOrderRepository(backend, store);
  final placeOrder = PlaceOrder(backend, orderRepository);
  final catalogViewModel = CatalogViewModel(catalogRepository, backend);
  final cartViewModel = CartViewModel(placeOrder);
  final ordersViewModel = OrdersViewModel(orderRepository);
  final app = ShopApp(
    backend,
    store,
    catalogViewModel,
    cartViewModel,
    ordersViewModel,
  );
  runApp(app);
}
