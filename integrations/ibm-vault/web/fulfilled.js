"use strict";
const $ = id => document.getElementById(id);
function text(tag, value, className) { const el = document.createElement(tag); el.textContent = value; if (className) el.className = className; return el; }
(async () => {
  try {
    const [response, configResponse] = await Promise.all([fetch('/api/fulfilled', { credentials: 'same-origin', cache: 'no-store' }), fetch('/api/admin/config', { cache: 'no-store' })]);
    if (!response.ok) throw new Error('Could not load fulfilled requests.');
    const data = await response.json();
    if (configResponse.ok) { const config = await configResponse.json(); if (config.website_origin) { $('brand-link').href = config.website_origin; $('catalog-link').href = config.website_origin; } }
    for (const record of data.requests) {
      const card = text('article', '', 'card request-card');
      card.append(text('h2', 'KV secret created'), text('p', record.id, 'request-id'));
      const dl = text('dl', '', 'request-meta');
      for (const [label, value] of Object.entries({ Path: '/' + data.namespace + '/' + record.plan.mount + '/' + record.plan.secret_path, 'Business Unit ID (self-reported)': record.plan.business_unit_id, 'UserID (self-reported)': record.plan.user_id, Completed: new Date(record.updated_at * 1000).toLocaleString(), Version: record.receipt.version, Status: 'Fulfilled' })) { dl.append(text('dt', label), text('dd', String(value ?? ''))); }
      card.append(dl); $('requests').append(card);
    }
    $('status').textContent = data.requests.length ? data.requests.length + ' fulfilled request(s).' : 'No fulfilled requests from this browser yet.';
  } catch (error) { $('status').textContent = error.message; }
})();
