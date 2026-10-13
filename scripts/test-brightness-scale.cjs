const assert = require('node:assert/strict');
const { toValue, toPosition } = require('../app/static/brightness.js');
assert.equal(toValue(0),0);
assert.equal(toValue(1000),255);
assert.equal(toPosition(0),0);
assert.equal(toPosition(255),1000);
for (let value=0;value<=12;value++) assert.equal(toValue(toPosition(value)),value);
assert.ok(toPosition(10)>400,'Single digits should occupy much of the slider');
let previous=0;
for(let position=0;position<=1000;position++) {
  const value=toValue(position);
  assert.ok(value>=previous && value<=255); previous=value;
}
console.log('Brightness scale passed: full range, monotonic curve, precise 0–12, fine lower half.');
