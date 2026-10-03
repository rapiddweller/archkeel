// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import type { OrderRepository } from "../domain/repository";
export const remote: OrderRepository = { async load() { return []; } };
