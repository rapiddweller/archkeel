import 'package:shop/data/services/demo_backend.dart';
import 'package:shop/data/services/memory_store.dart';
import 'package:shop/domain/catalog/catalog_repository.dart';
import 'package:shop/domain/catalog/product.dart';

class CachedCatalogRepository implements CatalogRepository {
  CachedCatalogRepository(this._backend, this._store);

  final DemoBackend _backend;
  final MemoryStore _store;

  @override
  bool isOnline() => _backend.isOnline();

  @override
  Future<List<Product>> loadCatalog() async {
    if (!_backend.isOnline()) return _store.readCatalog();
    final products = await _backend.fetchCatalog();
    _store.saveCatalog(products);
    return products;
  }
}
