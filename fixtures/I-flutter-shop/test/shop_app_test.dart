// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shop/data/repositories/cached_catalog_repository.dart';
import 'package:shop/data/repositories/memory_order_repository.dart';
import 'package:shop/data/services/demo_backend.dart';
import 'package:shop/data/services/memory_store.dart';
import 'package:shop/domain/catalog/catalog_repository.dart';
import 'package:shop/domain/catalog/product.dart';
import 'package:shop/domain/checkout/place_order.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/domain/orders/order_repository.dart';
import 'package:shop/presentation/shopping/cart/cart_view_model.dart';
import 'package:shop/presentation/shopping/catalog/catalog_view_model.dart';
import 'package:shop/presentation/orders/orders_view_model.dart';
import 'package:shop/app/shop_app.dart';

void main() {
  testWidgets('loads catalog, checks out, and opens the saved order', (
    tester,
  ) async {
    final shop = _TestShop();
    await tester.pumpWidget(shop.app);
    await tester.pumpAndSettle();

    expect(find.text('Trail Mix'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('open-orders')));
    await tester.pumpAndSettle();
    expect(find.text('No orders yet'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-trail-mix')));
    await tester.tap(find.byKey(const ValueKey('add-oat-bar')));
    await tester.tap(find.byKey(const ValueKey('open-cart')));
    await tester.pumpAndSettle();
    expect(find.text('Trail Mix × 1'), findsOneWidget);
    expect(find.text('\$3.99'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('increase-trail-mix')));
    await tester.pump();
    expect(find.text('Trail Mix × 2'), findsOneWidget);
    expect(find.text('Oat Bar × 1'), findsOneWidget);
    expect(find.text('Total \$9.47'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('place-order')));
    await tester.pumpAndSettle();
    expect(find.text('Order placed'), findsOneWidget);
    expect(shop.cart.lines, isEmpty);

    await tester.tap(find.byKey(const ValueKey('open-orders')));
    await tester.pumpAndSettle();
    expect(find.text('Order #1'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('order-1')));
    await tester.pumpAndSettle();
    expect(find.text('Order detail'), findsOneWidget);
    expect(find.text('Trail Mix × 2'), findsOneWidget);
    expect(find.text('Oat Bar × 1'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('offline cache and failed checkout keep the cart for retry', (
    tester,
  ) async {
    final shop = _TestShop();
    await tester.pumpWidget(shop.app);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-trail-mix')));
    await tester.tap(find.byKey(const ValueKey('toggle-online')));
    await tester.pumpAndSettle();
    expect(find.text('Trail Mix'), findsOneWidget);
    expect(find.text('Offline: cached catalog'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('open-cart')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('place-order')));
    await tester.pumpAndSettle();
    expect(
      find.text('Checkout failed. Check your connection and try again.'),
      findsOneWidget,
    );
    expect(find.text('Trail Mix × 1'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('toggle-online')));
    await tester.pumpAndSettle();
    shop.backend.failNextRequest();
    await tester.tap(find.byKey(const ValueKey('open-cart')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('place-order')));
    await tester.pumpAndSettle();
    expect(
      find.text('Checkout failed. Check your connection and try again.'),
      findsOneWidget,
    );
    expect(find.text('Trail Mix × 1'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('place-order')));
    await tester.pumpAndSettle();
    expect(find.text('Order placed'), findsOneWidget);
    expect(shop.cart.lines, isEmpty);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('toggle-online')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('open-orders')));
    await tester.pumpAndSettle();
    expect(find.text('Offline: cached orders'), findsOneWidget);
    expect(find.text('Order #1'), findsOneWidget);
    expect(
      await MemoryOrderRepository(shop.backend, shop.store).loadAll(),
      hasLength(1),
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('catalog request errors can be retried', (tester) async {
    final shop = _TestShop();
    shop.backend.failNextRequest();
    await tester.pumpWidget(shop.app);
    await tester.pumpAndSettle();
    expect(find.text('Could not load catalog'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('retry-catalog')));
    await tester.pumpAndSettle();
    expect(find.text('Trail Mix'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('offline mode restores cached products after a failed refresh', (
    tester,
  ) async {
    final shop = _TestShop();
    await tester.pumpWidget(shop.app);
    await tester.pumpAndSettle();
    expect(find.text('Trail Mix'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('toggle-online')));
    await tester.pumpAndSettle();
    shop.backend.failNextRequest();
    await tester.tap(find.byKey(const ValueKey('toggle-online')));
    await tester.pumpAndSettle();
    expect(find.text('Could not load catalog'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('toggle-online')));
    await tester.pumpAndSettle();
    expect(find.text('Offline: cached catalog'), findsOneWidget);
    expect(find.text('Trail Mix'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('ignores duplicate checkout taps while submission is pending', (
    tester,
  ) async {
    final orders = _ControlledOrderRepository();
    final shop = _TestShop(orderRepository: orders);
    await tester.pumpWidget(shop.app);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-trail-mix')));
    await tester.tap(find.byKey(const ValueKey('open-cart')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('place-order')));
    await tester.pump();
    expect(
      tester
          .widget<IconButton>(find.byKey(const ValueKey('increase-trail-mix')))
          .onPressed,
      isNull,
    );
    shop.cart.addProduct(const Product('apple', 'Apple', 99));
    expect(shop.cart.lines, hasLength(1));
    await tester.tap(find.byKey(const ValueKey('place-order')));
    await tester.pump();
    expect(orders.placeCalls, 1);
    expect(find.text('Placing order…'), findsOneWidget);

    await tester.pageBack();
    await tester.pump();
    expect(
      tester
          .widget<IconButton>(find.byKey(const ValueKey('add-oat-bar')))
          .onPressed,
      isNull,
    );

    orders.completePending();
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<IconButton>(find.byKey(const ValueKey('add-oat-bar')))
          .onPressed,
      isNotNull,
    );
    await tester.tap(find.byKey(const ValueKey('open-cart')));
    await tester.pumpAndSettle();
    expect(find.text('Order placed'), findsOneWidget);
    expect(orders.placeCalls, 1);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('unmount cancels the order stream and ignores pending loads', (
    tester,
  ) async {
    final catalog = _ControlledCatalogRepository();
    final orders = _ControlledOrderRepository(pendingLoad: true);
    final shop = _TestShop(catalogRepository: catalog, orderRepository: orders);
    final storeClosed = Completer<void>();
    shop.store.watchOrders().listen((_) {}, onDone: storeClosed.complete);

    await tester.pumpWidget(shop.app);
    expect(find.text('Loading catalog…'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await expectLater(orders.cancelled.future, completes);
    await expectLater(storeClosed.future, completes);

    catalog.pendingLoad.complete(const [Product('late', 'Late item', 100)]);
    orders.pendingLoad!.complete(const []);
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}

class _TestShop {
  _TestShop({
    DemoBackend? backend,
    MemoryStore? store,
    CatalogRepository? catalogRepository,
    OrderRepository? orderRepository,
  }) : backend = backend ?? DemoBackend(),
       store = store ?? MemoryStore() {
    final catalog =
        catalogRepository ?? CachedCatalogRepository(this.backend, this.store);
    final orders =
        orderRepository ?? MemoryOrderRepository(this.backend, this.store);
    catalogViewModel = CatalogViewModel(catalog, this.backend);
    cart = CartViewModel(PlaceOrder(this.backend, orders));
    ordersViewModel = OrdersViewModel(orders);
    app = ShopApp(
      this.backend,
      this.store,
      catalogViewModel,
      cart,
      ordersViewModel,
    );
  }

  final DemoBackend backend;
  final MemoryStore store;
  late final CatalogViewModel catalogViewModel;
  late final CartViewModel cart;
  late final OrdersViewModel ordersViewModel;
  late final ShopApp app;
}

class _ControlledCatalogRepository implements CatalogRepository {
  final Completer<List<Product>> pendingLoad = Completer<List<Product>>();

  @override
  bool isOnline() => true;

  @override
  Future<List<Product>> loadCatalog() => pendingLoad.future;
}

class _ControlledOrderRepository implements OrderRepository {
  _ControlledOrderRepository({bool pendingLoad = false})
    : pendingOrder = Completer<Order>(),
      pendingLoad = pendingLoad ? Completer<List<Order>>() : null {
    _changes = StreamController<List<Order>>.broadcast(
      onCancel: () {
        if (!cancelled.isCompleted) cancelled.complete();
      },
    );
  }

  final Completer<Order> pendingOrder;
  final Completer<List<Order>>? pendingLoad;
  final Completer<void> cancelled = Completer<void>();
  late final StreamController<List<Order>> _changes;
  late Order submittedOrder;
  int placeCalls = 0;

  @override
  Future<Order> place(Order order) {
    placeCalls++;
    submittedOrder = order;
    return pendingOrder.future;
  }

  void completePending() => pendingOrder.complete(submittedOrder);

  @override
  Future<List<Order>> loadAll() =>
      pendingLoad?.future ?? Future.value(const []);

  @override
  Stream<List<Order>> watchAll() => _changes.stream;

  @override
  Future<Order?> findById(String id) async => null;
}
