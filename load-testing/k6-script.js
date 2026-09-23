import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

// Usage:
//   k6 run -e TARGET_URL=https://your-domain load-testing/k6-script.js
// Never point this at prod without a scheduled, sign-off exercise - see
// docs/OPERATIONS.md.

const target = __ENV.TARGET_URL || 'http://localhost';
const homepageLatency = new Trend('homepage_latency');
const healthLatency = new Trend('health_latency');

export const options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '3m', target: 100 },
    { duration: '2m', target: 500 },
    { duration: '3m', target: 500 },
    { duration: '2m', target: 1000 },
    { duration: '3m', target: 1000 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // matches docs/OPERATIONS.md
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const home = http.get(`${target}/`);
  homepageLatency.add(home.timings.duration);
  check(home, { 'homepage status is 200': (r) => r.status === 200 });

  const health = http.get(`${target}/health`);
  healthLatency.add(health.timings.duration);
  check(health, { 'health status is 200': (r) => r.status === 200 });

  sleep(1);
}
