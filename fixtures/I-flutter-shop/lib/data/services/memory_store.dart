import 'dart:async';

import 'package:shop/domain/catalog/product.dart';
import 'package:shop/domain/orders/order.dart';

class MemoryStore {
  MemoryStore();

  final StreamController<List<Order>> _orderChanges =
      StreamController.broadcast();
  List<Product> _catalog = const [];
  final Map<String, Order> _orders = {};

  List<Product> readCatalog() => List.unmodifiable(_catalog);

  void saveCatalog(List<Product> products) =>
      _catalog = List.unmodifiable(products);

  List<Order> readOrders() => List.unmodifiable(_orders.values);

  void saveOrders(List<Order> orders) {
    _orders
      ..clear()
      ..addEntries(orders.map((order) => MapEntry(order.id, order)));
    _orderChanges.add(readOrders());
  }

  Order? findOrder(String id) => _orders[id];

  Stream<List<Order>> watchOrders() => _orderChanges.stream;

  Future<void> dispose() => _orderChanges.close();
}
