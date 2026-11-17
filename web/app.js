const $ = (selector) => document.querySelector(selector);
const state = { orders: [], flights: [] };
const nextStatus = { created: 'picked_up', planned: 'picked_up', picked_up: 'in_transit', in_transit: 'delivered' };
const statusLabel = (status) => ({ created: 'Created', planned: 'Planned', picked_up: 'Picked up', in_transit: 'In transit', delivered: 'Delivered', failed: 'Failed' }[status] || status);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

function showNotice(message, type = 'success') {
  const notice = $('#notice');
  notice.textContent = message;
  notice.className = `notice show ${type}`;
  window.clearTimeout(showNotice.timeout);
  showNotice.timeout = window.setTimeout(() => { notice.className = 'notice'; }, 4200);
}

function renderOrders() {
  const search = $('#order-search').value.trim().toLowerCase();
  const priority = $('#priority-filter').value;
  const filtered = state.orders.filter((order) => {
    const matchesSearch = [order.reference, order.recipient, order.pickup, order.dropoff].join(' ').toLowerCase().includes(search);
    return matchesSearch && (priority === 'all' || order.priority === priority);
  });
  $('#order-total').textContent = state.orders.length;
  $('#nav-order-count').textContent = state.orders.filter((order) => !['delivered', 'failed'].includes(order.status)).length;
  $('#orders-shown').textContent = `Showing ${filtered.length} of ${state.orders.length} deliveries`;
  $('#orders-body').innerHTML = filtered.length ? filtered.map((order) => {
    const action = nextStatus[order.status];
    const actionHtml = action ? `<button class="row-action" data-advance="${order.id}" title="Advance to ${statusLabel(action)}">${statusLabel(action)} →</button>` : `<span class="muted-empty">—</span>`;
    return `<tr>
      <td><button class="order-code track-trigger" data-track="${order.id}" aria-label="Show tracking timeline for ${escapeHtml(order.reference)}">${escapeHtml(order.reference)}</button></td>
      <td><span class="recipient">${escapeHtml(order.recipient)}</span></td>
      <td><span class="route">${escapeHtml(order.pickup)} <span>→</span> ${escapeHtml(order.dropoff)}</span></td>
      <td><span class="weight">${Number(order.package_weight_kg).toFixed(1)} kg</span></td>
      <td><span class="priority ${escapeHtml(order.priority)}">${escapeHtml(order.priority)}</span></td>
      <td><span class="status ${escapeHtml(order.status)}">${escapeHtml(statusLabel(order.status))}</span></td>
      <td>${actionHtml}</td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" class="empty-cell">No matching deliveries. Create an order to get started.</td></tr>';
  document.querySelectorAll('[data-advance]').forEach((button) => button.addEventListener('click', () => advanceOrder(button.dataset.advance)));
  document.querySelectorAll('[data-track]').forEach((button) => button.addEventListener('click', () => toggleTimeline(button)));
  renderAssignOptions();
}

async function toggleTimeline(button) {
  const existing = button.closest('tr').nextElementSibling;
  if (existing && existing.classList.contains('tracking-row')) { existing.remove(); return; }
  try {
    const order = await api(`/api/orders/${button.dataset.track}`);
    const events = order.events.map((event) => {
      const when = new Date(event.occurred_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
      return `<div class="timeline-item"><span class="timeline-dot ${escapeHtml(event.status)}"></span><div><strong>${escapeHtml(statusLabel(event.status))}</strong><span>${escapeHtml(event.location || 'Location not recorded')} · ${escapeHtml(when)}</span>${event.note ? `<small>${escapeHtml(event.note)}</small>` : ''}</div></div>`;
    }).join('');
    const row = document.createElement('tr');
    row.className = 'tracking-row';
    row.innerHTML = `<td colspan="7"><div class="timeline"><div class="timeline-heading">Parcel timeline <span>${escapeHtml(order.reference)}</span></div>${events || '<div class="muted-empty">No tracking events recorded.</div>'}</div></td>`;
    button.closest('tr').after(row);
  } catch (error) { showNotice(error.message, 'error'); }
}

function renderFlights() {
  $('#flight-total').textContent = `${state.flights.length} planned`;
  $('#metric-flights').textContent = state.flights.length;
  $('#flight-list').innerHTML = state.flights.length ? state.flights.map((flight) => {
    const departure = new Date(flight.departure_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    return `<article class="flight-card">
      <div><div class="flight-name">${escapeHtml(flight.flight_code)} <span class="status planned">Planned</span></div><div class="flight-time">${escapeHtml(departure)} · ${escapeHtml(flight.drone_id)} · ${escapeHtml(flight.pilot)}</div></div>
      <div class="flight-load">${Number(flight.assigned_weight_kg).toFixed(1)} / ${Number(flight.capacity_kg).toFixed(1)} kg</div>
      <div class="flight-route">${escapeHtml(flight.origin)} → ${escapeHtml(flight.destination)}</div>
      <div class="flight-time">${flight.assigned_count} ${flight.assigned_count === 1 ? 'parcel' : 'parcels'}</div>
    </article>`;
  }).join('') : '<div class="muted-empty">No flights planned yet. Create a route above.</div>';
  renderAssignOptions();
}

function renderAssignOptions() {
  const flightSelect = $('#assign-flight');
  const orderSelect = $('#assign-order');
  const flightValue = flightSelect.value;
  const orderValue = orderSelect.value;
  flightSelect.innerHTML = '<option value="">Select flight</option>' + state.flights.map((flight) => `<option value="${flight.id}">${escapeHtml(flight.flight_code)} · ${escapeHtml(flight.origin)} → ${escapeHtml(flight.destination)}</option>`).join('');
  orderSelect.innerHTML = '<option value="">Select order</option>' + state.orders.filter((order) => ['created', 'planned'].includes(order.status) && !order.flight).map((order) => `<option value="${order.id}">${escapeHtml(order.reference)} · ${escapeHtml(order.dropoff)} · ${Number(order.package_weight_kg).toFixed(1)} kg</option>`).join('');
  if (state.flights.some((flight) => String(flight.id) === flightValue)) flightSelect.value = flightValue;
  if ([...orderSelect.options].some((option) => option.value === orderValue)) orderSelect.value = orderValue;
}

function renderMetrics() {
  const active = state.orders.filter((order) => !['delivered', 'failed'].includes(order.status));
  $('#metric-active').textContent = active.length;
  $('#metric-active-foot').textContent = `${state.orders.length} total orders`;
  $('#metric-awaiting').textContent = state.orders.filter((order) => order.status === 'created' && !order.flight).length;
  $('#metric-delivered').textContent = state.orders.filter((order) => order.status === 'delivered').length;
}

async function refresh() {
  try {
    const [orders, flights] = await Promise.all([api('/api/orders'), api('/api/flights')]);
    state.orders = orders.items;
    state.flights = flights.items;
    renderMetrics();
    renderOrders();
    renderFlights();
  } catch (error) {
    showNotice(error.message, 'error');
    $('#orders-body').innerHTML = '<tr><td colspan="7" class="empty-cell">Could not connect to the OMS API.</td></tr>';
  }
}

async function advanceOrder(id) {
  const order = state.orders.find((item) => String(item.id) === String(id));
  if (!order || !nextStatus[order.status]) return;
  const next = nextStatus[order.status];
  try {
    await api(`/api/orders/${id}/events`, { method: 'POST', body: JSON.stringify({ status: next, location: next === 'delivered' ? order.dropoff : order.pickup, note: `Marked ${statusLabel(next).toLowerCase()} by operations` }) });
    await refresh();
    showNotice(`${order.reference} updated to ${statusLabel(next).toLowerCase()}.`);
  } catch (error) { showNotice(error.message, 'error'); }
}

$('#order-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  data.package_weight_kg = Number(data.package_weight_kg);
  try {
    const order = await api('/api/orders', { method: 'POST', body: JSON.stringify(data) });
    event.currentTarget.reset();
    event.currentTarget.elements.pickup.value = 'North Hub';
    await refresh();
    showNotice(`Delivery ${order.reference} added to the dispatch queue.`);
  } catch (error) { showNotice(error.message, 'error'); }
});

$('#flight-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  data.capacity_kg = Number(data.capacity_kg);
  try {
    const flight = await api('/api/flights', { method: 'POST', body: JSON.stringify(data) });
    event.currentTarget.reset();
    event.currentTarget.elements.origin.value = 'North Hub';
    await refresh();
    $('#assign-flight').value = flight.id;
    showNotice(`Flight ${flight.flight_code} planned. Assign matching parcels below.`);
  } catch (error) { showNotice(error.message, 'error'); }
});

$('#assign-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    const result = await api(`/api/flights/${data.flight_id}/assign`, { method: 'POST', body: JSON.stringify({ order_id: Number(data.order_id) }) });
    const order = state.orders.find((item) => String(item.id) === data.order_id);
    await refresh();
    showNotice(`${order ? order.reference : 'Delivery'} assigned to ${result.flight_code}.`);
  } catch (error) { showNotice(error.message, 'error'); }
});

$('#order-search').addEventListener('input', renderOrders);
$('#priority-filter').addEventListener('change', renderOrders);
$('#new-order-jump').addEventListener('click', () => $('#order-form').elements.reference.focus());
refresh();
