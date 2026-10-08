import 'package:flutter/foundation.dart';
import 'package:shop/domain/catalog/catalog_repository.dart';
import 'package:shop/domain/catalog/product.dart';
import 'package:shop/domain/checkout/shop_status.dart';
import 'package:shop/state/async_state.dart';

class CatalogViewModel extends ChangeNotifier {
  CatalogViewModel(this._repository, this._status) {
    load();
  }

  final CatalogRepository _repository;
  final ShopStatus _status;
  AsyncState<List<Product>> _state = const AsyncState(
    LoadPhase.loading,
    null,
    null,
  );
  bool _disposed = false;

  AsyncState<List<Product>> get state => _state;

  bool get isOnline => _repository.isOnline();

  Future<void> load() async {
    _state = const AsyncState(LoadPhase.loading, null, null);
    _notify();
    try {
      final products = await _repository.loadCatalog();
      _state = AsyncState(
        products.isEmpty ? LoadPhase.empty : LoadPhase.ready,
        products,
        null,
      );
    } catch (error) {
      _state = AsyncState(LoadPhase.failed, null, error);
    }
    _notify();
  }

  Future<void> retry() => load();

  Future<void> setOnline(bool online) async {
    _status.setOnline(online);
    if (online) {
      await load();
    } else {
      final cached = _state.value;
      _state = AsyncState(
        cached == null || cached.isEmpty ? LoadPhase.empty : LoadPhase.ready,
        cached ?? const [],
        null,
      );
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
