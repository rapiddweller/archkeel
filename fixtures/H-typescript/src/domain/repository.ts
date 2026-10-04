// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

import type { Order } from "./order";
export interface OrderRepository { load(): Promise<Order[]>; }
