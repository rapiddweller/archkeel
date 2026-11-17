// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites of a library (AD-796 S2), through the survey. Each plant is a Dart package that
//! `dart analyze` accepts with no error.

use serde_json::Value;

use crate::import_survey::tests::run_roots;
use crate::import_survey::Survey;

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.4.0\n";

fn survey(files: &[(&str, &str)]) -> Survey {
    let mut all = vec![("pubspec.yaml", PUBSPEC)];
    all.extend_from_slice(files);
    run_roots(&all, &["lib"])
}

/// The status and the targets of the call written as `expression` in the scope `scope`.
fn call(found: &Survey, scope: &str, expression: &str) -> (String, Vec<String>) {
    let record = found
        .calls
        .iter()
        .map(|record| serde_json::to_value(record).unwrap_or(Value::Null))
        .find(|record| {
            record["data"]["expression"] == expression
                && record["data"]["source_scope"]
                    .as_str()
                    .is_some_and(|text| text.ends_with(scope))
        });
    let Some(record) = record else {
        return ("absent".to_owned(), Vec::new());
    };
    let targets = record["data"]["targets"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| item.as_str().map(str::to_owned))
        .collect();
    (
        record["data"]["status"].as_str().unwrap_or("").to_owned(),
        targets,
    )
}

fn resolved(target: &str) -> (String, Vec<String>) {
    ("resolved".to_owned(), vec![target.to_owned()])
}

#[test]
fn a_member_of_the_class_hides_a_function_of_the_library() {
    let found = survey(&[(
        "lib/a.dart",
        "void save() {}\nclass A {\n  void save() {}\n  void run() {\n    save();\n  }\n}\n",
    )]);
    // 4.0.1 read the library first and gave `shop.a.save`.
    assert_eq!(call(&found, "A.run", "save()"), resolved("shop.a.A.save"));
}

#[test]
fn a_function_of_the_library_hides_an_inherited_member() {
    let found = survey(&[(
        "lib/a.dart",
        "void foo() {}\nclass A {\n  void foo() {}\n}\nclass B extends A {\n  void run() {\n    foo();\n  }\n}\n",
    )]);
    // The members of A are no names of the scope of B; an implicit `this` comes last.
    assert_eq!(call(&found, "B.run", "foo()"), resolved("shop.a.foo"));
}

#[test]
fn an_inherited_member_binds_only_without_a_name_of_the_library() {
    let found = survey(&[(
        "lib/a.dart",
        "class A {\n  void foo() {}\n}\nclass B extends A {\n  void run() {\n    foo();\n  }\n}\n",
    )]);
    assert_eq!(call(&found, "B.run", "foo()"), resolved("shop.a.A.foo"));
}

#[test]
fn a_member_that_only_a_base_outside_the_snapshot_can_declare_stays_unresolved() {
    let found = survey(&[(
        "lib/a.dart",
        "import 'dart:collection';\nclass A extends ListBase<int> {\n  @override\n  int length = 0;\n  @override\n  int operator [](int i) => 0;\n  @override\n  void operator []=(int i, int v) {}\n  void run() {\n    clear();\n  }\n}\n",
    )]);
    assert_eq!(call(&found, "A.run", "clear()").1, Vec::<String>::new());
    assert_ne!(call(&found, "A.run", "clear()").0, "resolved");
}

#[test]
fn a_receiver_takes_the_class_of_its_constructor() {
    let found = survey(&[(
        "lib/a.dart",
        "class Repo {\n  void save() {}\n}\nvoid main() {\n  final repo = Repo();\n  repo.save();\n}\n",
    )]);
    assert_eq!(
        call(&found, "main", "repo.save()"),
        resolved("shop.a.Repo.save")
    );
}

#[test]
fn a_named_constructor_and_a_static_method_bind_through_their_class() {
    let found = survey(&[
        (
            "lib/a.dart",
            "class A {\n  A._make();\n  static A make() => A._make();\n}\n",
        ),
        (
            "lib/b.dart",
            "import 'a.dart';\nvoid main() {\n  A.make();\n}\n",
        ),
    ]);
    // A construction names its class as the target, as 4.0.1 writes it.
    assert_eq!(call(&found, "A.make", "A._make()"), resolved("shop.a.A"));
    assert_eq!(call(&found, "main", "A.make()"), resolved("shop.a.A.make"));
}
