import 'package:flutter/foundation.dart';
import 'package:shop/domain/cart/cart.dart';
import 'package:shop/domain/catalog/product.dart';
import 'package:shop/domain/checkout/place_order.dart';
import 'package:shop/domain/orders/order.dart';
import 'package:shop/state/async_state.dart';

class CartViewModel extends ChangeNotifier {
  CartViewModel(this._placeOrder);

  final PlaceOrder _placeOrder;
  final Cart _cart = Cart();
  AsyncState<Order> _state = const AsyncState(LoadPhase.idle, null, null);
  bool _isPlacingOrder = false;
  bool _disposed = false;

  List<CartLine> get lines => _cart.lines;

  int get totalCents => _cart.totalCents;

  bool get isPlacingOrder => _isPlacingOrder;

  AsyncState<Order> get state => _state;

  void addProduct(Product product) {
    if (_isPlacingOrder) return;
    _cart.add(product);
    _notify();
  }

  void setQuantity(String productId, int quantity) {
    if (_isPlacingOrder) return;
    _cart.setQuantity(productId, quantity);
    _notify();
  }

  Future<Order?> checkout() async {
    if (_isPlacingOrder || _cart.lines.isEmpty) return null;
    _isPlacingOrder = true;
    _state = const AsyncState(LoadPhase.loading, null, null);
    _notify();
    try {
      final order = await _placeOrder.call(_cart);
      _cart.clear();
      _state = AsyncState(LoadPhase.ready, order, null);
      return order;
    } catch (error) {
      _state = AsyncState(LoadPhase.failed, null, error);
      return null;
    } finally {
      _isPlacingOrder = false;
      _notify();
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
