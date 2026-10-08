import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/domain/orders/order_repository.dart';
import 'package:shop/state/async_state.dart';

class OrdersViewModel extends ChangeNotifier {
  OrdersViewModel(this._repository) {
    load();
  }

  final OrderRepository _repository;
  AsyncState<List<Order>> _state = const AsyncState(
    LoadPhase.loading,
    null,
    null,
  );
  StreamSubscription<List<Order>>? _ordersSubscription;
  bool _disposed = false;

  AsyncState<List<Order>> get state => _state;

  Future<void> load() async {
    _ordersSubscription ??= _repository.watchAll().listen(_receiveOrders);
    try {
      final orders = await _repository.loadAll();
      _receiveOrders(orders);
    } catch (error) {
      _state = AsyncState(LoadPhase.failed, null, error);
      _notify();
    }
  }

  Future<Order?> findById(String id) => _repository.findById(id);

  void _receiveOrders(List<Order> orders) {
    if (_disposed) return;
    _state = AsyncState(
      orders.isEmpty ? LoadPhase.empty : LoadPhase.ready,
      orders,
      null,
    );
    notifyListeners();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _ordersSubscription?.cancel();
    super.dispose();
  }
}
