import React, { useState, useEffect, useMemo } from 'react';

const API_BASE = 'http://127.0.0.1:5000/api';

export default function App() {
  // Navigation & Role states
  const [activeTab, setActiveTab] = useState('dashboard');
  const [facilities, setFacilities] = useState([]);
  const [selectedFacility, setSelectedFacility] = useState('');
  const [userRole, setUserRole] = useState('Pharmacist');
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  // Data states
  const [dashboardData, setDashboardData] = useState(null);
  const [medicines, setMedicines] = useState([]);
  const [batches, setBatches] = useState([]);
  const [stockList, setStockList] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [alertsData, setAlertsData] = useState(null);
  const [reportData, setReportData] = useState(null);

  // UI state
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Search & Filter
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('ALL');

  // Transaction Form state
  const [transForm, setTransForm] = useState({
    batch_id: '',
    transaction_type: 'ISSUE',
    quantity: '',
    facility_name: '',
    related_facility: '',
    reason: '',
    reference_number: '',
    performed_by: 'Pharmacist S. Suresh',
    adjustment_direction: 'IN'
  });

  // Medicine Form state
  const [medForm, setMedForm] = useState({
    medicine_code: '',
    name: '',
    strength: '',
    category: 'Essential Medicine',
    unit: 'Tablets',
    min_stock_level: 500
  });

  // Batch Form state
  const [batchForm, setBatchForm] = useState({
    medicine_id: '',
    batch_number: '',
    supplier: 'Tamil Nadu Medical Services Corp (TNMSC)',
    received_date: new Date().toISOString().split('T')[0],
    expiry_date: '',
    received_quantity: 1000,
    facility_name: 'Central Medical Store - Coimbatore'
  });

  // Load Initial Facilities & Core Data
  useEffect(() => {
    fetchFacilities();
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Reload data whenever facility filter changes
  useEffect(() => {
    loadAllData();
  }, [selectedFacility]);

  // Set default facility for transaction form when facility changes
  useEffect(() => {
    if (selectedFacility) {
      setTransForm(prev => ({ ...prev, facility_name: selectedFacility }));
    } else if (facilities.length > 0) {
      setTransForm(prev => ({ ...prev, facility_name: facilities[1]?.name || facilities[0]?.name }));
    }
  }, [selectedFacility, facilities]);

  const showToast = (msg, isErr = false) => {
    if (isErr) {
      setErrorMsg(msg);
      setTimeout(() => setErrorMsg(''), 6000);
    } else {
      setSuccessMsg(msg);
      setTimeout(() => setSuccessMsg(''), 5000);
    }
  };

  const fetchFacilities = async () => {
    try {
      const res = await fetch(`${API_BASE}/facilities`);
      if (res.ok) {
        const data = await res.json();
        setFacilities(data);
      }
    } catch (err) {
      console.error("Failed to load facilities:", err);
    }
  };

  const loadAllData = async () => {
    setLoading(true);
    const facQuery = selectedFacility ? `?facility=${encodeURIComponent(selectedFacility)}` : '';
    try {
      const [dashRes, medsRes, batchRes, stockRes, transRes, alertsRes, repRes] = await Promise.all([
        fetch(`${API_BASE}/dashboard${facQuery}`),
        fetch(`${API_BASE}/medicines${facQuery}`),
        fetch(`${API_BASE}/batches${facQuery}`),
        fetch(`${API_BASE}/stock${facQuery}`),
        fetch(`${API_BASE}/transactions${facQuery}`),
        fetch(`${API_BASE}/alerts${facQuery}`),
        fetch(`${API_BASE}/reports/stock${facQuery}`)
      ]);

      if (dashRes.ok) setDashboardData(await dashRes.json());
      if (medsRes.ok) setMedicines(await medsRes.json());
      if (batchRes.ok) setBatches(await batchRes.json());
      if (stockRes.ok) setStockList(await stockRes.json());
      if (transRes.ok) setTransactions(await transRes.json());
      if (alertsRes.ok) setAlertsData(await alertsRes.json());
      if (repRes.ok) setReportData(await repRes.json());
    } catch (err) {
      showToast('Could not communicate with Flask backend API at ' + API_BASE, true);
    } finally {
      setLoading(false);
    }
  };

  // Handle Record Transaction
  const handleRecordTransaction = async (e) => {
    e.preventDefault();
    if (!transForm.batch_id || !transForm.quantity || !transForm.facility_name) {
      showToast('Please select a batch, enter valid quantity, and specify facility.', true);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/transactions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...transForm,
          quantity: parseInt(transForm.quantity, 10),
          performed_by: `${userRole} (${transForm.performed_by})`
        })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Transaction rejected by server.', true);
      } else {
        showToast(data.message || 'Movement successfully registered in the ledger!');
        setTransForm({
          ...transForm,
          quantity: '',
          reason: '',
          reference_number: ''
        });
        loadAllData();
      }
    } catch (err) {
      showToast('Network error while recording transaction: ' + err.message, true);
    }
  };

  // Handle Add Medicine
  const handleCreateMedicine = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/medicines`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...medForm,
          min_stock_level: parseInt(medForm.min_stock_level || 0, 10)
        })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Failed to register medicine.', true);
      } else {
        showToast(`Medicine ${data.name} (${data.medicine_code}) registered successfully!`);
        setMedForm({
          medicine_code: '',
          name: '',
          strength: '',
          category: 'Essential Medicine',
          unit: 'Tablets',
          min_stock_level: 500
        });
        loadAllData();
      }
    } catch (err) {
      showToast('Error registering medicine: ' + err.message, true);
    }
  };

  // Handle Add Batch
  const handleCreateBatch = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/batches`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...batchForm,
          received_quantity: parseInt(batchForm.received_quantity, 10),
          performed_by: `${userRole} (${batchForm.facility_name})`
        })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Failed to register batch.', true);
      } else {
        showToast(`Batch ${data.batch_number} registered and stock ledger credited!`);
        setBatchForm({
          medicine_id: '',
          batch_number: '',
          supplier: 'Tamil Nadu Medical Services Corp (TNMSC)',
          received_date: new Date().toISOString().split('T')[0],
          expiry_date: '',
          received_quantity: 1000,
          facility_name: facilities[0]?.name || 'Central Medical Store - Coimbatore'
        });
        loadAllData();
      }
    } catch (err) {
      showToast('Error registering batch: ' + err.message, true);
    }
  };

  // Handle Update Min-Stock Threshold
  const handleUpdateThreshold = async (medicine_id, currentThreshold) => {
    const newVal = prompt('Enter new minimum stock threshold level:', currentThreshold);
    if (newVal === null) return;
    const intVal = parseInt(newVal, 10);
    if (isNaN(intVal) || intVal < 0) {
      showToast('Threshold must be a non-negative number.', true);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/settings/threshold`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ medicine_id, min_stock_level: intVal })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`Minimum stock threshold updated to ${intVal} units.`);
        loadAllData();
      } else {
        showToast(data.error || 'Failed to update threshold.', true);
      }
    } catch (err) {
      showToast('Error updating threshold: ' + err.message, true);
    }
  };

  // Reset Sample Data
  const handleResetSampleData = async () => {
    if (!confirm('Reload default government PHC sample demonstration data?')) return;
    try {
      const res = await fetch(`${API_BASE}/seed`, { method: 'POST' });
      if (res.ok) {
        showToast('Sample demonstration data reloaded successfully!');
        loadAllData();
      }
    } catch (err) {
      showToast('Failed to reset sample data: ' + err.message, true);
    }
  };

  // Export Report to CSV
  const exportToCSV = () => {
    if (!reportData?.report_data) return;
    const headers = ['Medicine Code', 'Name', 'Strength', 'Category', 'Unit', 'Min Threshold', 'Total Stock', 'Usable Stock', 'Status', 'Daily Burn Rate', 'Days Remaining'];
    const rows = reportData.report_data.map(r => [
      `"${r.medicine_code}"`,
      `"${r.name}"`,
      `"${r.strength}"`,
      `"${r.category}"`,
      `"${r.unit}"`,
      r.min_stock_level,
      r.total_stock,
      r.usable_stock,
      `"${r.status}"`,
      r.daily_burn_rate,
      r.estimated_days_remaining
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `NalamCare_Stock_Report_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Filtered Stock list
  const filteredStock = useMemo(() => {
    return stockList.filter(s => {
      const q = searchTerm.toLowerCase();
      const matchSearch = (
        s.medicine_name.toLowerCase().includes(q) ||
        s.medicine_code.toLowerCase().includes(q) ||
        s.batch_number.toLowerCase().includes(q) ||
        s.facility_name.toLowerCase().includes(q)
      );
      if (!matchSearch) return false;
      if (typeFilter === 'EXPIRED' && s.shelf_life_status !== 'EXPIRED') return false;
      if (typeFilter === 'EXPIRING_30' && s.shelf_life_status !== 'EXPIRING_30_DAYS') return false;
      if (typeFilter === 'GOOD' && s.shelf_life_status !== 'GOOD') return false;
      return true;
    });
  }, [stockList, searchTerm, typeFilter]);

  // Selected batch information for transaction form
  const selectedBatchInfo = useMemo(() => {
    if (!transForm.batch_id) return null;
    return batches.find(b => b.id.toString() === transForm.batch_id.toString());
  }, [transForm.batch_id, batches]);

  // Current stock for selected batch at the chosen facility
  const availableAtFacility = useMemo(() => {
    if (!transForm.batch_id || !transForm.facility_name) return 0;
    const item = stockList.find(s => 
      s.batch_id.toString() === transForm.batch_id.toString() && 
      s.facility_name === transForm.facility_name
    );
    return item ? item.current_stock : 0;
  }, [transForm.batch_id, transForm.facility_name, stockList]);

  return (
    <div className="app-container">
      {/* 1. Header with Government Branding & Controls */}
      <header className="app-header">
        <div className="header-top">
          <div className="brand-section">
            <div className="logo-badge">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
                <path d="M12 5v14" />
                <path d="M5 12h14" />
              </svg>
            </div>
            <div>
              <div className="brand-title">
                NalamCare
                <span style={{ fontSize: '0.65rem', background: '#38bdf8', color: '#0369a1', padding: '0.15rem 0.5rem', borderRadius: '9999px', fontWeight: 800 }}>
                  PHC STOCK-OUT EARLY WARNING
                </span>
              </div>
              <div className="brand-subtitle">Department of Public Health & Preventive Medicine, Tamil Nadu</div>
            </div>
          </div>

          <div className="header-controls">
            {/* Connectivity Badge */}
            <div className="control-badge" style={{ color: isOnline ? '#86efac' : '#fca5a5' }}>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: isOnline ? '#22c55e' : '#ef4444' }}></span>
              {isOnline ? 'PHC Central Sync Online' : 'Offline Mode (Local Cache)'}
            </div>

            {/* Facility Selector */}
            <div className="control-badge">
              <span>Facility:</span>
              <select 
                className="control-select"
                value={selectedFacility} 
                onChange={(e) => setSelectedFacility(e.target.value)}
              >
                <option value="">All Facilities (District View)</option>
                {facilities.map(f => (
                  <option key={f.id} value={f.name}>{f.name} ({f.type})</option>
                ))}
              </select>
            </div>

            {/* Role Switcher */}
            <div className="control-badge">
              <span>Role:</span>
              <select 
                className="control-select"
                value={userRole} 
                onChange={(e) => setUserRole(e.target.value)}
              >
                <option value="Store Keeper">Store Keeper</option>
                <option value="Pharmacist">Pharmacist</option>
                <option value="Medical Officer">Medical Officer</option>
                <option value="District Administrator">District Admin</option>
              </select>
            </div>
          </div>
        </div>
      </header>

      {/* 2. Demonstration Prototype Disclaimer Banner */}
      <div className="disclaimer-banner">
        <div>
          <strong>DEMONSTRATION PROTOTYPE:</strong> Realistic sample government PHC inventory data loaded for demonstration purposes. Not connected to live production hospital databases.
        </div>
        <button className="disclaimer-btn" onClick={handleResetSampleData}>
          ↻ Reset Sample Demonstration Data
        </button>
      </div>

      {/* Toast Notifications */}
      {errorMsg && (
        <div style={{ maxWidth: '1400px', margin: '1rem auto 0 auto', width: '100%', padding: '0 1.5rem' }}>
          <div className="alert-banner danger">
            <span style={{ fontSize: '1.2rem' }}>⚠️</span>
            <div><strong>Error:</strong> {errorMsg}</div>
          </div>
        </div>
      )}
      {successMsg && (
        <div style={{ maxWidth: '1400px', margin: '1rem auto 0 auto', width: '100%', padding: '0 1.5rem' }}>
          <div className="alert-banner success">
            <span style={{ fontSize: '1.2rem' }}>✓</span>
            <div><strong>Success:</strong> {successMsg}</div>
          </div>
        </div>
      )}

      {/* 3. Navigation Tabs */}
      <nav className="nav-bar">
        <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
          📊 Dashboard Overview
        </button>
        <button className={`nav-tab ${activeTab === 'stock' ? 'active' : ''}`} onClick={() => setActiveTab('stock')}>
          📦 Facility Inventory
        </button>
        <button className={`nav-tab ${activeTab === 'movement' ? 'active' : ''}`} onClick={() => setActiveTab('movement')}>
          🔄 Stock Movements & Transfers
        </button>
        <button className={`nav-tab ${activeTab === 'medicines' ? 'active' : ''}`} onClick={() => setActiveTab('medicines')}>
          💊 Essential Medicines Master
        </button>
        <button className={`nav-tab ${activeTab === 'batches' ? 'active' : ''}`} onClick={() => setActiveTab('batches')}>
          🏷️ Batches & Shelf-Life
        </button>
        <button className={`nav-tab ${activeTab === 'alerts' ? 'active' : ''}`} onClick={() => setActiveTab('alerts')}>
          ⚠️ Early Warnings & Alerts
          {dashboardData?.kpis?.medicines_at_stockout_risk > 0 && (
            <span className="nav-badge">{dashboardData.kpis.medicines_at_stockout_risk}</span>
          )}
        </button>
        <button className={`nav-tab ${activeTab === 'reports' ? 'active' : ''}`} onClick={() => setActiveTab('reports')}>
          📑 Consumption & Burn-Rate Audit
        </button>
      </nav>

      {/* 4. Tab Content */}
      <main className="main-content">
        {loading && (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--slate-500)' }}>
            <p>Synchronizing PHC inventory with central ledger...</p>
          </div>
        )}

        {/* --- TAB 1: DASHBOARD OVERVIEW --- */}
        {!loading && activeTab === 'dashboard' && dashboardData && (
          <div>
            {/* KPI Cards */}
            <div className="kpi-grid">
              <div className="kpi-card">
                <div>
                  <div className="kpi-title">Essential Medicines</div>
                  <div className="kpi-value">{dashboardData.kpis.total_medicines}</div>
                  <div className="kpi-subtext">Active catalogue types</div>
                </div>
                <div className="kpi-icon primary">💊</div>
              </div>

              <div className="kpi-card">
                <div>
                  <div className="kpi-title">Active Batches</div>
                  <div className="kpi-value">{dashboardData.kpis.total_active_batches}</div>
                  <div className="kpi-subtext">Batches with positive stock</div>
                </div>
                <div className="kpi-icon success">🏷️</div>
              </div>

              <div className="kpi-card">
                <div>
                  <div className="kpi-title">Available Usable Units</div>
                  <div className="kpi-value">{dashboardData.kpis.total_usable_stock_units.toLocaleString()}</div>
                  <div className="kpi-subtext">Excludes expired stock</div>
                </div>
                <div className="kpi-icon primary">📦</div>
              </div>

              <div className="kpi-card">
                <div>
                  <div className="kpi-title">Stock-Out Risks</div>
                  <div className="kpi-value" style={{ color: dashboardData.kpis.medicines_at_stockout_risk > 0 ? 'var(--danger)' : 'var(--success)' }}>
                    {dashboardData.kpis.medicines_at_stockout_risk}
                  </div>
                  <div className="kpi-subtext">Below configured safety minimum</div>
                </div>
                <div className="kpi-icon danger">⚠️</div>
              </div>

              <div className="kpi-card">
                <div>
                  <div className="kpi-title">Near-Expiry (&lt;30d)</div>
                  <div className="kpi-value" style={{ color: dashboardData.kpis.near_expiry_30_days_count > 0 ? 'var(--warning)' : 'inherit' }}>
                    {dashboardData.kpis.near_expiry_30_days_count}
                  </div>
                  <div className="kpi-subtext">{dashboardData.kpis.near_expiry_60_days_count} expiring in 60d</div>
                </div>
                <div className="kpi-icon warning">⏳</div>
              </div>
            </div>

            {/* Dashboard Two-Column Section */}
            <div className="dashboard-grid">
              {/* Left Column: Early Warning Forecast & Movements */}
              <div>
                {/* Early Warning Radar */}
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <span>⚡</span> Stock-Out Early Warning Radar (Consumption Velocity Forecast)
                    </div>
                    <span className="badge badge-danger">Algorithmic Forecast</span>
                  </div>
                  <div className="card-body">
                    {alertsData?.forecast_warnings?.length === 0 ? (
                      <p style={{ color: 'var(--slate-500)', fontSize: '0.85rem' }}>
                        No imminent stock-out predicted within the next 14 days at current consumption velocity.
                      </p>
                    ) : (
                      alertsData?.forecast_warnings?.map((fw, idx) => (
                        <div key={idx} className="forecast-card">
                          <div className="forecast-header">
                            <div>
                              <strong style={{ fontSize: '1rem', color: 'var(--slate-900)' }}>{fw.medicine_name} ({fw.strength})</strong>
                              <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>Code: {fw.medicine_code}</div>
                            </div>
                            <div className="days-counter">~{fw.estimated_days} DAYS REMAINING</div>
                          </div>
                          <p style={{ fontSize: '0.82rem', color: 'var(--slate-700)', margin: '0.25rem 0' }}>
                            {fw.message}
                          </p>
                          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                            <button 
                              className="btn btn-primary btn-sm"
                              onClick={() => {
                                setTransForm(prev => ({
                                  ...prev,
                                  transaction_type: 'TRANSFER_OUT',
                                  reason: `Early warning restock indent for ${fw.medicine_name}`
                                }));
                                setActiveTab('movement');
                              }}
                            >
                              Dispatch Restock Indent
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Recent Stock Movements */}
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <span>🔄</span> Recent Stock Movements (Live Audit Ledger)
                    </div>
                    <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab('movement')}>
                      View Full Ledger
                    </button>
                  </div>
                  <div className="card-body" style={{ padding: 0 }}>
                    <div className="table-responsive">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Type</th>
                            <th>Medicine & Batch</th>
                            <th>Qty</th>
                            <th>Facility</th>
                            <th>Operator</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dashboardData.recent_movements?.map((t) => (
                            <tr key={t.id}>
                              <td style={{ fontSize: '0.78rem', color: 'var(--slate-500)' }}>{t.transaction_date}</td>
                              <td>
                                <span className={`badge ${
                                  t.transaction_type === 'RECEIPT' ? 'badge-success' :
                                  t.transaction_type === 'ISSUE' ? 'badge-info' :
                                  t.transaction_type === 'TRANSFER_IN' ? 'badge-success' :
                                  t.transaction_type === 'TRANSFER_OUT' ? 'badge-warning' :
                                  t.transaction_type === 'EXPIRED' ? 'badge-danger' : 'badge-neutral'
                                }`}>
                                  {t.transaction_type}
                                </span>
                              </td>
                              <td>
                                <strong>{t.medicine_name}</strong>
                                <div style={{ fontSize: '0.72rem', color: 'var(--slate-400)' }}>Batch: {t.batch_number}</div>
                              </td>
                              <td style={{ fontWeight: 700 }}>
                                {['ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT'].includes(t.transaction_type) ? `-${t.quantity}` : `+${t.quantity}`}
                              </td>
                              <td style={{ fontSize: '0.8rem' }}>
                                {t.facility_name}
                                {t.related_facility && (
                                  <div style={{ fontSize: '0.7rem', color: 'var(--slate-400)' }}>⇄ {t.related_facility}</div>
                                )}
                              </td>
                              <td style={{ fontSize: '0.78rem', color: 'var(--slate-500)' }}>{t.performed_by || 'Store Staff'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Expiry Alerts & Fast Actions */}
              <div>
                {/* Critical Expiry Watch */}
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <span>⏳</span> Near-Expiry Batches Watch
                    </div>
                    <span className="badge badge-warning">&lt; 60 Days</span>
                  </div>
                  <div className="card-body">
                    {alertsData?.expiring_within_30_days?.length === 0 && alertsData?.expiring_within_60_days?.length === 0 ? (
                      <p style={{ color: 'var(--slate-500)', fontSize: '0.85rem' }}>No near-expiry batches detected.</p>
                    ) : (
                      <>
                        {alertsData?.expiring_within_30_days?.map((item, i) => (
                          <div key={`30-${i}`} style={{ borderLeft: '4px solid var(--danger)', padding: '0.5rem 0.75rem', background: '#fef2f2', marginBottom: '0.5rem', borderRadius: '4px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <strong>{item.medicine_name}</strong>
                              <span className="badge badge-danger">{item.days_to_expiry} days</span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--slate-600)' }}>
                              Batch: {item.batch_number} | Stock: {item.quantity} units @ {item.facility_name}
                            </div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--slate-500)', marginTop: '0.2rem' }}>
                              Expiry Date: {item.expiry_date}
                            </div>
                          </div>
                        ))}

                        {alertsData?.expiring_within_60_days?.map((item, i) => (
                          <div key={`60-${i}`} style={{ borderLeft: '4px solid var(--warning)', padding: '0.5rem 0.75rem', background: '#fffbeb', marginBottom: '0.5rem', borderRadius: '4px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <strong>{item.medicine_name}</strong>
                              <span className="badge badge-warning">{item.days_to_expiry} days</span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--slate-600)' }}>
                              Batch: {item.batch_number} | Stock: {item.quantity} units @ {item.facility_name}
                            </div>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                </div>

                {/* Quick Shortcuts */}
                <div className="card">
                  <div className="card-header">
                    <div className="card-title">
                      <span>⚡</span> Primary Health Centre Shortcuts
                    </div>
                  </div>
                  <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                    <button className="btn btn-primary" onClick={() => setActiveTab('movement')}>
                      <span>➕</span> Record OPD Dispensing / Stock Movement
                    </button>
                    <button className="btn btn-secondary" onClick={() => setActiveTab('medicines')}>
                      <span>💊</span> Register New Medicine Catalogue Item
                    </button>
                    <button className="btn btn-secondary" onClick={() => setActiveTab('batches')}>
                      <span>🏷️</span> Receive New Consignment Batch
                    </button>
                    <button className="btn btn-secondary" onClick={() => setActiveTab('reports')}>
                      <span>📊</span> Generate State Inventory Audit Report
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* --- TAB 2: FACILITY INVENTORY --- */}
        {!loading && activeTab === 'stock' && (
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <span>📦</span> Facility Current Medicine Inventory
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <select 
                  className="form-control"
                  style={{ width: 'auto' }}
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                >
                  <option value="ALL">All Batches</option>
                  <option value="GOOD">Safe Shelf-Life</option>
                  <option value="EXPIRING_30">Expiring in 30 Days</option>
                  <option value="EXPIRED">Expired Batches</option>
                </select>
              </div>
            </div>
            <div className="card-body">
              <div className="toolbar">
                <input 
                  type="text" 
                  className="form-control search-input" 
                  placeholder="🔍 Search medicine, code, batch, facility..." 
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
                <div style={{ fontSize: '0.85rem', color: 'var(--slate-500)' }}>
                  Showing <strong>{filteredStock.length}</strong> batch allocations
                </div>
              </div>

              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Medicine Name</th>
                      <th>Strength</th>
                      <th>Category</th>
                      <th>Batch Number</th>
                      <th>Facility</th>
                      <th>Current Stock</th>
                      <th>Expiry Date</th>
                      <th>Shelf-Life Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStock.length === 0 ? (
                      <tr>
                        <td colSpan="9" style={{ textAlign: 'center', padding: '2rem', color: 'var(--slate-400)' }}>
                          No matching stock records found.
                        </td>
                      </tr>
                    ) : (
                      filteredStock.map((s, idx) => (
                        <tr key={idx}>
                          <td>
                            <strong>{s.medicine_name}</strong>
                            <div style={{ fontSize: '0.72rem', color: 'var(--slate-400)' }}>{s.medicine_code}</div>
                          </td>
                          <td>{s.strength}</td>
                          <td>{s.category}</td>
                          <td><code>{s.batch_number}</code></td>
                          <td>{s.facility_name}</td>
                          <td style={{ fontWeight: 800, fontSize: '0.95rem' }}>
                            {s.current_stock.toLocaleString()} {s.unit}
                          </td>
                          <td>{s.expiry_date}</td>
                          <td>
                            <span className={`badge ${
                              s.shelf_life_status === 'EXPIRED' ? 'badge-danger' :
                              s.shelf_life_status === 'EXPIRING_30_DAYS' ? 'badge-danger' :
                              s.shelf_life_status === 'EXPIRING_60_DAYS' ? 'badge-warning' : 'badge-success'
                            }`}>
                              {s.shelf_life_status === 'EXPIRED' ? 'EXPIRED' :
                               s.shelf_life_status === 'EXPIRING_30_DAYS' ? `${s.days_to_expiry}d left` :
                               s.shelf_life_status === 'EXPIRING_60_DAYS' ? `${s.days_to_expiry}d left` : 'SAFE'}
                            </span>
                          </td>
                          <td>
                            <button 
                              className="btn btn-secondary btn-sm"
                              onClick={() => {
                                setTransForm(prev => ({
                                  ...prev,
                                  batch_id: s.batch_id.toString(),
                                  facility_name: s.facility_name,
                                  transaction_type: 'ISSUE'
                                }));
                                setActiveTab('movement');
                              }}
                            >
                              Issue / Move
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* --- TAB 3: STOCK MOVEMENTS & TRANSACTIONS --- */}
        {!loading && activeTab === 'movement' && (
          <div>
            {/* Record Transaction Form */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>➕</span> Record New Stock Movement (Double-Entry Inventory Ledger)
                </div>
              </div>
              <div className="card-body">
                <form onSubmit={handleRecordTransaction}>
                  <div className="form-grid">
                    {/* Transaction Type */}
                    <div className="form-group">
                      <label>Movement Type *</label>
                      <select 
                        className="form-control"
                        value={transForm.transaction_type}
                        onChange={(e) => setTransForm({ ...transForm, transaction_type: e.target.value })}
                        required
                      >
                        <option value="ISSUE">ISSUE (Dispense to OPD/IPD Patient/Ward)</option>
                        <option value="RECEIPT">RECEIPT (Received from Supplier/Warehouse)</option>
                        <option value="TRANSFER_OUT">TRANSFER_OUT (Inter-Facility Transfer)</option>
                        <option value="RETURN">RETURN (Patient/Sub-centre Return to Store)</option>
                        <option value="DAMAGE">DAMAGE (Broken / Compromised Packaging)</option>
                        <option value="EXPIRED">EXPIRED (Disposal & Quarantine Write-Off)</option>
                        <option value="ADJUSTMENT">ADJUSTMENT (Audit Reconciliation)</option>
                      </select>
                    </div>

                    {/* Batch Selection */}
                    <div className="form-group">
                      <label>Medicine Batch *</label>
                      <select 
                        className="form-control"
                        value={transForm.batch_id}
                        onChange={(e) => setTransForm({ ...transForm, batch_id: e.target.value })}
                        required
                      >
                        <option value="">-- Select Medicine Batch --</option>
                        {batches.map(b => (
                          <option key={b.id} value={b.id}>
                            {b.medicine_name} — Batch {b.batch_number} (Exp: {b.expiry_date})
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Facility */}
                    <div className="form-group">
                      <label>Originating Facility *</label>
                      <select 
                        className="form-control"
                        value={transForm.facility_name}
                        onChange={(e) => setTransForm({ ...transForm, facility_name: e.target.value })}
                        required
                      >
                        <option value="">-- Select Facility --</option>
                        {facilities.map(f => (
                          <option key={f.id} value={f.name}>{f.name}</option>
                        ))}
                      </select>
                    </div>

                    {/* Target Facility (if transfer) */}
                    {transForm.transaction_type === 'TRANSFER_OUT' && (
                      <div className="form-group">
                        <label>Destination Facility *</label>
                        <select 
                          className="form-control"
                          value={transForm.related_facility}
                          onChange={(e) => setTransForm({ ...transForm, related_facility: e.target.value })}
                          required
                        >
                          <option value="">-- Select Destination Facility --</option>
                          {facilities
                            .filter(f => f.name !== transForm.facility_name)
                            .map(f => (
                              <option key={f.id} value={f.name}>{f.name}</option>
                            ))
                          }
                        </select>
                      </div>
                    )}

                    {/* Quantity */}
                    <div className="form-group">
                      <label>Quantity Units *</label>
                      <input 
                        type="number" 
                        min="1"
                        className="form-control" 
                        placeholder="e.g. 100"
                        value={transForm.quantity}
                        onChange={(e) => setTransForm({ ...transForm, quantity: e.target.value })}
                        required
                      />
                      {['ISSUE', 'DAMAGE', 'EXPIRED', 'TRANSFER_OUT'].includes(transForm.transaction_type) && transForm.facility_name && transForm.batch_id && (
                        <span style={{ fontSize: '0.75rem', color: availableAtFacility > 0 ? 'var(--secondary)' : 'var(--danger)', fontWeight: 600 }}>
                          Available at this facility: {availableAtFacility} units
                        </span>
                      )}
                    </div>

                    {/* Reference Number */}
                    <div className="form-group">
                      <label>Reference / Indent Number</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="Auto-generated if empty"
                        value={transForm.reference_number}
                        onChange={(e) => setTransForm({ ...transForm, reference_number: e.target.value })}
                      />
                    </div>

                    {/* Reason */}
                    <div className="form-group">
                      <label>Reason / Clinical Purpose</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Daily OPD Dispensing, Emergency Ward indent"
                        value={transForm.reason}
                        onChange={(e) => setTransForm({ ...transForm, reason: e.target.value })}
                      />
                    </div>

                    {/* Operator */}
                    <div className="form-group">
                      <label>Operator / Staff Name</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        value={transForm.performed_by}
                        onChange={(e) => setTransForm({ ...transForm, performed_by: e.target.value })}
                      />
                    </div>
                  </div>

                  <div style={{ marginTop: '1.25rem', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                    <button type="button" className="btn btn-secondary" onClick={() => setTransForm({ ...transForm, quantity: '', reason: '' })}>
                      Clear Form
                    </button>
                    <button type="submit" className="btn btn-primary">
                      ✓ Post Transaction to Ledger
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Audit Trail Table */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>📜</span> Complete Immutable Transaction Ledger (Audit Trail)
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--slate-500)' }}>
                  Total records: {transactions.length}
                </div>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <div className="table-responsive">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Medicine</th>
                        <th>Batch</th>
                        <th>Quantity</th>
                        <th>Facility</th>
                        <th>Related Facility</th>
                        <th>Reference</th>
                        <th>Reason</th>
                        <th>Operator</th>
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map(t => (
                        <tr key={t.id}>
                          <td><code>#{t.id}</code></td>
                          <td>{t.transaction_date}</td>
                          <td>
                            <span className={`badge ${
                              t.transaction_type === 'RECEIPT' ? 'badge-success' :
                              t.transaction_type === 'ISSUE' ? 'badge-info' :
                              t.transaction_type === 'TRANSFER_IN' ? 'badge-success' :
                              t.transaction_type === 'TRANSFER_OUT' ? 'badge-warning' :
                              t.transaction_type === 'EXPIRED' ? 'badge-danger' : 'badge-neutral'
                            }`}>
                              {t.transaction_type}
                            </span>
                          </td>
                          <td><strong>{t.medicine_name}</strong></td>
                          <td><code>{t.batch_number}</code></td>
                          <td style={{ fontWeight: 800 }}>{t.quantity}</td>
                          <td>{t.facility_name}</td>
                          <td>{t.related_facility || '—'}</td>
                          <td><code>{t.reference_number || '—'}</code></td>
                          <td style={{ fontSize: '0.8rem', color: 'var(--slate-600)' }}>{t.reason || '—'}</td>
                          <td style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>{t.performed_by}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* --- TAB 4: MEDICINES MASTER & THRESHOLDS --- */}
        {!loading && activeTab === 'medicines' && (
          <div>
            {/* Register Medicine Form */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>💊</span> Register Essential Medicine (NLEM / EDL)
                </div>
              </div>
              <div className="card-body">
                <form onSubmit={handleCreateMedicine}>
                  <div className="form-grid">
                    <div className="form-group">
                      <label>Medicine Code * (Unique)</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. MED-AZI-500"
                        value={medForm.medicine_code}
                        onChange={(e) => setMedForm({ ...medForm, medicine_code: e.target.value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label>Medicine Name *</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Azithromycin"
                        value={medForm.name}
                        onChange={(e) => setMedForm({ ...medForm, name: e.target.value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label>Strength *</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. 500 mg, 100 ml, 40 IU"
                        value={medForm.strength}
                        onChange={(e) => setMedForm({ ...medForm, strength: e.target.value })}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label>Category</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. Antibiotic, Analgesic, Maternal Health"
                        value={medForm.category}
                        onChange={(e) => setMedForm({ ...medForm, category: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Unit of Issue *</label>
                      <select 
                        className="form-control"
                        value={medForm.unit}
                        onChange={(e) => setMedForm({ ...medForm, unit: e.target.value })}
                        required
                      >
                        <option value="Tablets">Tablets</option>
                        <option value="Capsules">Capsules</option>
                        <option value="Vials">Vials</option>
                        <option value="Bottles">Bottles</option>
                        <option value="Sachets">Sachets</option>
                        <option value="Ampoules">Ampoules</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Minimum Stock Level Threshold</label>
                      <input 
                        type="number" 
                        min="0"
                        className="form-control" 
                        placeholder="0 = unconfigured threshold"
                        value={medForm.min_stock_level}
                        onChange={(e) => setMedForm({ ...medForm, min_stock_level: e.target.value })}
                      />
                      <span style={{ fontSize: '0.72rem', color: 'var(--slate-500)' }}>
                        Triggers stock-out alert when usable stock drops below this number
                      </span>
                    </div>
                  </div>

                  <div style={{ marginTop: '1.25rem', display: 'flex', justifyContent: 'flex-end' }}>
                    <button type="submit" className="btn btn-primary">
                      ✓ Register Medicine in Catalogue
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Medicines List with Configurable Thresholds */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>📋</span> Essential Medicines Catalogue & Threshold Manager
                </div>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <div className="table-responsive">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Name</th>
                        <th>Strength</th>
                        <th>Category</th>
                        <th>Unit</th>
                        <th>Usable Stock</th>
                        <th>Configured Min Threshold</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {medicines.map(m => (
                        <tr key={m.id}>
                          <td><code>{m.medicine_code}</code></td>
                          <td><strong>{m.name}</strong></td>
                          <td>{m.strength}</td>
                          <td>{m.category}</td>
                          <td>{m.unit}</td>
                          <td style={{ fontWeight: 800 }}>{m.usable_stock.toLocaleString()}</td>
                          <td>
                            {m.min_stock_level > 0 ? (
                              <span>{m.min_stock_level} {m.unit}</span>
                            ) : (
                              <span style={{ color: 'var(--slate-400)', fontStyle: 'italic' }}>Unconfigured</span>
                            )}
                          </td>
                          <td>
                            <span className={`badge ${
                              m.threshold_status === 'Below Minimum Threshold' ? 'badge-danger' :
                              m.threshold_status === 'Out of Stock' ? 'badge-danger' :
                              m.threshold_status === 'Adequate Stock' ? 'badge-success' : 'badge-neutral'
                            }`}>
                              {m.threshold_status}
                            </span>
                          </td>
                          <td>
                            <button 
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleUpdateThreshold(m.id, m.min_stock_level)}
                            >
                              ⚙️ Edit Threshold
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* --- TAB 5: BATCHES & SHELF-LIFE --- */}
        {!loading && activeTab === 'batches' && (
          <div>
            {/* Register Batch Form */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>🏷️</span> Receive & Register New Consignment Batch
                </div>
              </div>
              <div className="card-body">
                <form onSubmit={handleCreateBatch}>
                  <div className="form-grid">
                    <div className="form-group">
                      <label>Medicine *</label>
                      <select 
                        className="form-control"
                        value={batchForm.medicine_id}
                        onChange={(e) => setBatchForm({ ...batchForm, medicine_id: e.target.value })}
                        required
                      >
                        <option value="">-- Select Medicine --</option>
                        {medicines.map(m => (
                          <option key={m.id} value={m.id}>{m.name} ({m.strength}) - {m.medicine_code}</option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Batch Number *</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        placeholder="e.g. PAR-2026-B3"
                        value={batchForm.batch_number}
                        onChange={(e) => setBatchForm({ ...batchForm, batch_number: e.target.value })}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Supplier / Manufacturer *</label>
                      <input 
                        type="text" 
                        className="form-control" 
                        value={batchForm.supplier}
                        onChange={(e) => setBatchForm({ ...batchForm, supplier: e.target.value })}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Received Date * (ISO)</label>
                      <input 
                        type="date" 
                        className="form-control" 
                        value={batchForm.received_date}
                        onChange={(e) => setBatchForm({ ...batchForm, received_date: e.target.value })}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Expiry Date * (ISO)</label>
                      <input 
                        type="date" 
                        className="form-control" 
                        value={batchForm.expiry_date}
                        onChange={(e) => setBatchForm({ ...batchForm, expiry_date: e.target.value })}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Received Quantity *</label>
                      <input 
                        type="number" 
                        min="1"
                        className="form-control" 
                        value={batchForm.received_quantity}
                        onChange={(e) => setBatchForm({ ...batchForm, received_quantity: e.target.value })}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label>Receiving Facility *</label>
                      <select 
                        className="form-control"
                        value={batchForm.facility_name}
                        onChange={(e) => setBatchForm({ ...batchForm, facility_name: e.target.value })}
                        required
                      >
                        {facilities.map(f => (
                          <option key={f.id} value={f.name}>{f.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div style={{ marginTop: '1.25rem', display: 'flex', justifyContent: 'flex-end' }}>
                    <button type="submit" className="btn btn-primary">
                      ✓ Register Batch & Credit Stock Ledger
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Batches Table */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>🏷️</span> Registered Batches & Shelf-Life Tracker
                </div>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <div className="table-responsive">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Batch Number</th>
                        <th>Medicine</th>
                        <th>Supplier</th>
                        <th>Received Date</th>
                        <th>Expiry Date</th>
                        <th>Initial Consignment</th>
                        <th>Current System Stock</th>
                        <th>Shelf-Life Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batches.map(b => (
                        <tr key={b.id}>
                          <td><code>{b.batch_number}</code></td>
                          <td><strong>{b.medicine_name}</strong> ({b.strength})</td>
                          <td style={{ fontSize: '0.8rem' }}>{b.supplier}</td>
                          <td>{b.received_date}</td>
                          <td>{b.expiry_date}</td>
                          <td>{b.received_quantity} {b.unit}</td>
                          <td style={{ fontWeight: 800 }}>{b.current_stock} {b.unit}</td>
                          <td>
                            <span className={`badge ${
                              b.expiry_status === 'EXPIRED' ? 'badge-danger' :
                              b.expiry_status === 'CRITICAL_NEAR_EXPIRY' ? 'badge-danger' :
                              b.expiry_status === 'WARNING_NEAR_EXPIRY' ? 'badge-warning' : 'badge-success'
                            }`}>
                              {b.expiry_status} ({b.days_to_expiry}d)
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* --- TAB 6: ALERTS & EARLY WARNINGS HUB --- */}
        {!loading && activeTab === 'alerts' && alertsData && (
          <div>
            {/* Early Warning Forecast Radar */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>⚡</span> Consumption Burn-Rate Early Warning Alerts
                </div>
                <span className="badge badge-danger">14-Day Lookahead</span>
              </div>
              <div className="card-body">
                {alertsData.forecast_warnings.length === 0 ? (
                  <p style={{ color: 'var(--slate-500)' }}>No medicine is forecast to stock out within 14 days.</p>
                ) : (
                  alertsData.forecast_warnings.map((fw, i) => (
                    <div key={i} className="alert-banner warning">
                      <div>
                        <strong>{fw.medicine_name} ({fw.strength})</strong>
                        <div>{fw.message}</div>
                        <div style={{ marginTop: '0.5rem' }}>
                          <button 
                            className="btn btn-primary btn-sm"
                            onClick={() => {
                              setTransForm(prev => ({
                                ...prev,
                                transaction_type: 'TRANSFER_OUT',
                                reason: `Urgent stock-out avoidance for ${fw.medicine_name}`
                              }));
                              setActiveTab('movement');
                            }}
                          >
                            Dispatch Indent Transfer
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Threshold Stock-out Alerts */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>⚠️</span> Medicines Below Configured Safety Threshold
                </div>
              </div>
              <div className="card-body">
                {alertsData.stockout_alerts.length === 0 ? (
                  <p style={{ color: 'var(--slate-500)' }}>All medicines with configured thresholds have adequate stock.</p>
                ) : (
                  alertsData.stockout_alerts.map((al, i) => (
                    <div key={i} className="alert-banner danger">
                      <div>
                        <strong>{al.medicine_name} ({al.strength})</strong>
                        <div>{al.message}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Near Expiry Batches Alert */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>⏳</span> Near-Expiry Batches (&lt;30 and &lt;60 Days)
                </div>
              </div>
              <div className="card-body">
                {alertsData.expiring_within_30_days.length === 0 && alertsData.expiring_within_60_days.length === 0 ? (
                  <p style={{ color: 'var(--slate-500)' }}>No batches near expiry.</p>
                ) : (
                  <div className="table-responsive">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Batch Number</th>
                          <th>Medicine</th>
                          <th>Facility</th>
                          <th>Stock</th>
                          <th>Expiry Date</th>
                          <th>Days Left</th>
                          <th>Recommended Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {alertsData.expiring_within_30_days.map((b, i) => (
                          <tr key={`30-${i}`}>
                            <td><code>{b.batch_number}</code></td>
                            <td>{b.medicine_name}</td>
                            <td>{b.facility_name}</td>
                            <td><strong>{b.quantity}</strong></td>
                            <td>{b.expiry_date}</td>
                            <td><span className="badge badge-danger">{b.days_to_expiry} days</span></td>
                            <td>Prioritize for dispensing / Redistribution</td>
                          </tr>
                        ))}
                        {alertsData.expiring_within_60_days.map((b, i) => (
                          <tr key={`60-${i}`}>
                            <td><code>{b.batch_number}</code></td>
                            <td>{b.medicine_name}</td>
                            <td>{b.facility_name}</td>
                            <td><strong>{b.quantity}</strong></td>
                            <td>{b.expiry_date}</td>
                            <td><span className="badge badge-warning">{b.days_to_expiry} days</span></td>
                            <td>Monitor shelf-life velocity</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* --- TAB 7: CONSUMPTION & BURN-RATE REPORT --- */}
        {!loading && activeTab === 'reports' && reportData && (
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <span>📑</span> Stock Valuation, Consumption Velocity & Run-Rate Audit Report
              </div>
              <button className="btn btn-primary btn-sm" onClick={exportToCSV}>
                ⬇️ Export CSV Report
              </button>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Medicine</th>
                      <th>Category</th>
                      <th>Usable Stock</th>
                      <th>Min Safety Threshold</th>
                      <th>Status</th>
                      <th>Active Batches</th>
                      <th>30-Day Daily Burn Rate</th>
                      <th>Estimated Runway Days</th>
                      <th>Prediction Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.report_data?.map((r, i) => (
                      <tr key={i}>
                        <td>
                          <strong>{r.name}</strong> ({r.strength})
                          <div style={{ fontSize: '0.72rem', color: 'var(--slate-400)' }}>{r.medicine_code}</div>
                        </td>
                        <td>{r.category}</td>
                        <td style={{ fontWeight: 800 }}>{r.usable_stock.toLocaleString()} {r.unit}</td>
                        <td>{r.min_stock_level}</td>
                        <td>
                          <span className={`badge ${
                            r.status === 'Below Minimum Threshold' ? 'badge-danger' :
                            r.status === 'Out of Stock' ? 'badge-danger' :
                            r.status === 'Adequate Stock' ? 'badge-success' : 'badge-neutral'
                          }`}>
                            {r.status}
                          </span>
                        </td>
                        <td>{r.active_batch_count}</td>
                        <td style={{ fontWeight: 600 }}>
                          {r.daily_burn_rate !== 'N/A' ? `${r.daily_burn_rate} ${r.unit}/day` : '—'}
                        </td>
                        <td style={{ fontWeight: 800, color: r.estimated_days_remaining !== 'N/A' && r.estimated_days_remaining <= 14 ? 'var(--danger)' : 'inherit' }}>
                          {r.estimated_days_remaining !== 'N/A' ? `~${r.estimated_days_remaining} days` : '—'}
                        </td>
                        <td style={{ fontSize: '0.78rem', color: 'var(--slate-500)' }}>
                          {r.consumption_status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <div><strong>NalamCare</strong> — Public Health Centre Medicine Stock-Out Early Warning System</div>
        <div>Compliant with Tamil Nadu Medical Services Corporation (TNMSC) & National Health Mission (NHM) EDL Standards</div>
      </footer>
    </div>
  );
}
