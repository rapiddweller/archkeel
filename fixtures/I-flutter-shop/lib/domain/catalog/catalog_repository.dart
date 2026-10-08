import 'package:shop/domain/catalog/product.dart';

abstract interface class CatalogRepository {
  Future<List<Product>> loadCatalog();

  bool isOnline();
}
