const util = require("./util");
const { util: renamed } = require("./util");
const name = "./util";
const dynamic = require(name);
const joined = require("./" + "util");
const absent = require("./gone");
const fs = require("fs");
module.exports = { util, renamed, dynamic, joined, absent, fs };
