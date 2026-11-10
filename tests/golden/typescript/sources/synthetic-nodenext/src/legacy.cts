import fs = require("fs");
import helper = require("./helper.mjs");
export const old = fs;
export const loaded = () => import("./lib.js");
