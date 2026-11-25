(function () {
  const API = "/soja/api/producers";
  const SESSION_API = "/soja/api/session";
  const APP_ROOT = document.getElementById("soja-app");
  const ASSET_VERSION = (APP_ROOT && APP_ROOT.dataset && APP_ROOT.dataset.assetVersion) || "dev";
  const OFFLINE_DB_NAME = "soja_management_offline";
  const OFFLINE_DB_VERSION = 1;
  const OFFLINE_STORE = "kv";
  const SAVE_POINTS = [
    { lon: 2.41, lat: 8.02 },
    { lon: 2.42, lat: 8.02 },
    { lon: 2.42, lat: 8.01 },
    { lon: 2.41, lat: 8.01 },
  ];
  const DEFAULT_POINTS = [{ lon: null, lat: null }];

  const state = {
    view: "list",
    producers: [],
    selectedId: null,
    detailExploitationId: null,
    detailCooperativeId: null,
    detailFactoryId: null,
    detailBankId: null,
    query: "",
    campaign: "",
    notice: "",
    error: "",
    saving: false,
    locatingPointIndex: null,
    zoneLookupTimer: null,
    zoneLookupKey: "",
    zoneLookupPendingKey: "",
    session: null,
    isOnline: navigator.onLine !== false,
    syncingQueue: false,
    lastSyncAt: "",
    pendingWrites: 0,
    form: emptyProducer(),
    seedForm: emptyHarvest(),
    harvestForm: emptyHarvest(),
    partnerForm: emptyHarvest(),
  };
  let offlineDbPromise = null;
  let offlineQueue = [];
  let reconnectLogoutInProgress = false;
  let tempIdCounter = -1;

  function clone(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function uploadIcon() {
    return `<svg class="sync-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3v10m0-10 4 4m-4-4-4 4M5 15.5V17a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
    </svg>`;
  }

  function nextTempId() {
    tempIdCounter -= 1;
    return tempIdCounter;
  }

  function openOfflineDb() {
    if (!window.indexedDB) return Promise.resolve(null);
    if (offlineDbPromise) return offlineDbPromise;
    offlineDbPromise = new Promise((resolve, reject) => {
      const request = window.indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(OFFLINE_STORE)) {
          db.createObjectStore(OFFLINE_STORE, { keyPath: "key" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }).catch((error) => {
      offlineDbPromise = null;
      throw error;
    });
    return offlineDbPromise;
  }

  async function offlineGet(key) {
    const db = await openOfflineDb();
    if (!db) return null;
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(OFFLINE_STORE, "readonly");
      const store = transaction.objectStore(OFFLINE_STORE);
      const request = store.get(key);
      request.onsuccess = () => resolve(request.result ? request.result.value : null);
      request.onerror = () => reject(request.error);
    });
  }

  async function offlineSet(key, value) {
    const db = await openOfflineDb();
    if (!db) return;
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(OFFLINE_STORE, "readwrite");
      const store = transaction.objectStore(OFFLINE_STORE);
      const request = store.put({ key, value });
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async function offlineDelete(key) {
    const db = await openOfflineDb();
    if (!db) return;
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(OFFLINE_STORE, "readwrite");
      const store = transaction.objectStore(OFFLINE_STORE);
      const request = store.delete(key);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  function syncFormsFromSelected() {
    const producer = selectedProducer();
    state.form = producer ? clone(producer) : emptyProducer();
    state.seedForm = clone((producer && producer.harvest) || emptyHarvest());
    state.harvestForm = clone((producer && producer.harvest) || emptyHarvest());
    state.partnerForm = clone((producer && producer.harvest) || emptyHarvest());
  }

  function updateConnectivity() {
    state.isOnline = navigator.onLine !== false;
    render();
  }

  function isOfflineError(error) {
    if (!error) return false;
    return error.name === "TypeError" || /fetch/i.test(error.message || "") || !navigator.onLine;
  }

  async function persistOfflineState() {
    try {
      await offlineSet("snapshot", {
        session: state.session,
        producers: state.producers,
        selectedId: state.selectedId,
        view: state.view,
        lastSyncAt: state.lastSyncAt,
      });
      await offlineSet("queue", offlineQueue);
    } catch {
      return;
    }
  }

  async function restoreOfflineState() {
    try {
      const snapshot = await offlineGet("snapshot");
      const queue = await offlineGet("queue");
      if (Array.isArray(queue)) {
        offlineQueue = queue;
      }
      if (snapshot && typeof snapshot === "object") {
        state.session = snapshot.session || state.session;
        state.producers = Array.isArray(snapshot.producers) ? snapshot.producers : state.producers;
        state.selectedId = snapshot.selectedId || state.selectedId;
        state.view = snapshot.view || state.view;
        state.lastSyncAt = snapshot.lastSyncAt || state.lastSyncAt;
      }
      state.syncingQueue = false;
      state.isOnline = navigator.onLine !== false;
      state.notice = state.isOnline
        ? state.notice
        : "Mode hors ligne actif. Les dernières donnees locales sont chargees.";
      if (!state.selectedId && state.producers[0]) {
        state.selectedId = state.producers[0].id;
      }
      syncFormsFromSelected();
      state.pendingWrites = offlineQueue.length;
      return true;
    } catch {
      return false;
    }
  }

  function queueWrite(entry) {
    offlineQueue.push(entry);
    state.pendingWrites = offlineQueue.length;
    return persistOfflineState();
  }

  function replaceQueuedTempIds(fromId, toId) {
    offlineQueue = offlineQueue.map((entry) => {
      if (entry.url) {
        entry.url = entry.url.replace(new RegExp(String(fromId), "g"), String(toId));
      }
      if (entry.tempId === fromId) {
        entry.tempId = toId;
      }
      return entry;
    });
  }

  function removeProducerFromState(id) {
    state.producers = state.producers.filter((producer) => Number(producer.id) !== Number(id));
    if (Number(state.selectedId) === Number(id)) {
      state.selectedId = state.producers[0] ? state.producers[0].id : null;
    }
    syncFormsFromSelected();
  }

  function upsertProducerInState(producer) {
    const nextProducer = clone(producer);
    const index = state.producers.findIndex((item) => Number(item.id) === Number(nextProducer.id));
    if (index >= 0) {
      state.producers[index] = nextProducer;
    } else {
      state.producers.unshift(nextProducer);
    }
    state.selectedId = nextProducer.id;
    syncFormsFromSelected();
  }

  function updateProducerFromHarvest(producerId, updater) {
    const producer = state.producers.find((item) => Number(item.id) === Number(producerId));
    if (!producer) return null;
    producer.harvest = producer.harvest || emptyHarvest();
    updater(producer);
    if (Number(state.selectedId) === Number(producerId)) {
      syncFormsFromSelected();
    }
    return producer;
  }

  function updateProducerFromOperations(producerId, kind, operationPayload, operationId) {
    const producer = state.producers.find((item) => Number(item.id) === Number(producerId));
    if (!producer) return null;
    producer.exploitations = Array.isArray(producer.exploitations) ? producer.exploitations : [];
    const exploitation = producer.exploitations.find((item) => Number(item.id) === Number(operationPayload.exploitationId));
    if (!exploitation) return producer;
    const storageInfos = Array.isArray(exploitation.storageInfos) ? exploitation.storageInfos : (exploitation.storageInfos = []);
    const treatmentInfos = Array.isArray(exploitation.treatmentInfos) ? exploitation.treatmentInfos : (exploitation.treatmentInfos = []);
    const bankInfos = Array.isArray(exploitation.bankInfos) ? exploitation.bankInfos : (exploitation.bankInfos = []);
    const operationName = (state.session && state.session.user && state.session.user.name) || "SOJA";
    if (kind === "cooperative") {
      const payload = operationPayload.stock || {};
      const nextOperation = {
        id: operationId || nextTempId(),
        cooperativeId: operationPayload.cooperativeId || null,
        cooperativeName: operationName,
        type: payload.type || "",
        quantityT: payload.qtyT,
        date: payload.date || null,
        note: payload.note || "",
      };
      const index = storageInfos.findIndex((item) => Number(item.id) === Number(nextOperation.id));
      if (index >= 0) storageInfos[index] = nextOperation; else storageInfos.push(nextOperation);
      producer.harvest.stock = clone(payload);
      producer.harvest.shareStatus = operationPayload.shareStatus || producer.harvest.shareStatus;
    } else if (kind === "factory") {
      const payload = operationPayload.factoryProcess || {};
      const nextOperation = {
        id: operationId || nextTempId(),
        factoryId: operationPayload.factoryId || null,
        factoryName: operationName,
        storageInfoId: payload.storageInfoId || null,
        storageInfoLabel: payload.storageInfoLabel || "",
        dehull: !!payload.dehull,
        grind: !!payload.grind,
        date: payload.date || null,
        note: payload.note || "",
      };
      const index = treatmentInfos.findIndex((item) => Number(item.id) === Number(nextOperation.id));
      if (index >= 0) treatmentInfos[index] = nextOperation; else treatmentInfos.push(nextOperation);
      producer.harvest.factoryProcess = clone({
        dehull: nextOperation.dehull,
        grind: nextOperation.grind,
        storageInfoId: nextOperation.storageInfoId,
        storageInfoLabel: nextOperation.storageInfoLabel,
        date: nextOperation.date,
        note: nextOperation.note,
      });
      producer.harvest.shareStatus = operationPayload.shareStatus || producer.harvest.shareStatus;
    } else if (kind === "bank") {
      const payload = operationPayload.bankLoan || {};
      const nextOperation = {
        id: operationId || nextTempId(),
        bankId: operationPayload.bankId || null,
        bankName: operationName,
        borrowerType: payload.borrowerType || "",
        borrowerName: payload.borrowerName || "",
        requestedAmount: payload.requestedAmount,
        approvedAmount: payload.approvedAmount,
        riskLevel: payload.riskLevel || "",
        status: payload.status || "",
        date: payload.decisionDate || null,
        note: payload.note || "",
      };
      const index = bankInfos.findIndex((item) => Number(item.id) === Number(nextOperation.id));
      if (index >= 0) bankInfos[index] = nextOperation; else bankInfos.push(nextOperation);
      producer.harvest.bankLoan = clone({
        borrowerType: nextOperation.borrowerType,
        borrowerName: nextOperation.borrowerName,
        requestedAmount: nextOperation.requestedAmount,
        approvedAmount: nextOperation.approvedAmount,
        riskLevel: nextOperation.riskLevel,
        status: nextOperation.status,
        decisionDate: nextOperation.date,
        note: nextOperation.note,
      });
      producer.harvest.shareStatus = operationPayload.shareStatus || producer.harvest.shareStatus;
    }
    if (Number(state.selectedId) === Number(producerId)) {
      syncFormsFromSelected();
    }
    return producer;
  }

  function removeOperationFromState(producerId, kind, operationId, exploitationId) {
    const producer = state.producers.find((item) => Number(item.id) === Number(producerId));
    if (!producer) return null;
    producer.exploitations = Array.isArray(producer.exploitations) ? producer.exploitations : [];
    const exploitation = producer.exploitations.find((item) => Number(item.id) === Number(exploitationId));
    if (!exploitation) return producer;
    if (kind === "cooperative") {
      exploitation.storageInfos = (exploitation.storageInfos || []).filter((item) => Number(item.id) !== Number(operationId));
      const latest = exploitation.storageInfos[exploitation.storageInfos.length - 1];
      producer.harvest = producer.harvest || emptyHarvest();
      producer.harvest.stock = latest ? {
        type: latest.type || "",
        qtyT: latest.quantityT,
        date: latest.date || null,
        note: latest.note || "",
      } : { type: "", qtyT: null, date: null, note: "" };
    }
    if (kind === "factory") {
      exploitation.treatmentInfos = (exploitation.treatmentInfos || []).filter((item) => Number(item.id) !== Number(operationId));
      const latest = exploitation.treatmentInfos[exploitation.treatmentInfos.length - 1];
      producer.harvest = producer.harvest || emptyHarvest();
      producer.harvest.factoryProcess = latest ? {
        dehull: !!latest.dehull,
        grind: !!latest.grind,
        storageInfoId: latest.storageInfoId || null,
        storageInfoLabel: latest.storageInfoLabel || "",
        date: latest.date || null,
        note: latest.note || "",
      } : { dehull: false, grind: false, storageInfoId: null, storageInfoLabel: "", date: null, note: "" };
    }
    if (kind === "bank") {
      exploitation.bankInfos = (exploitation.bankInfos || []).filter((item) => Number(item.id) !== Number(operationId));
      const latest = exploitation.bankInfos[exploitation.bankInfos.length - 1];
      producer.harvest = producer.harvest || emptyHarvest();
      producer.harvest.bankLoan = latest ? {
        borrowerType: latest.borrowerType || "",
        borrowerName: latest.borrowerName || "",
        requestedAmount: latest.requestedAmount,
        approvedAmount: latest.approvedAmount,
        riskLevel: latest.riskLevel || "",
        status: latest.status || "",
        decisionDate: latest.date || null,
        note: latest.note || "",
      } : { borrowerType: "", borrowerName: "", requestedAmount: null, approvedAmount: null, riskLevel: "", status: "", decisionDate: null, note: "" };
    }
    if (Number(state.selectedId) === Number(producerId)) {
      syncFormsFromSelected();
    }
    return producer;
  }

  function emptyHarvest() {
    return {
      campaign: "2025 - 2026",
      exploitationId: null,
      exploitationName: "",
      seedDate: null,
      harvestForecastDate: null,
      harvestActualDate: null,
      forecastT: null,
      actualT: null,
      yieldTha: null,
      actualYieldTha: null,
      shareStatus: "partners",
      services: { drone: false, soil: false, training: false, finance: false },
      stock: { type: "", qtyT: null, date: null, note: "" },
      factoryProcess: { dehull: false, grind: false, date: null, note: "" },
      bankLoan: { borrowerType: "", borrowerName: "", requestedAmount: null, approvedAmount: null, riskLevel: "", status: "", decisionDate: null, note: "" },
    };
  }

  function emptyProducer() {
    return {
      externalId: `SoSoja-${Date.now()}`,
      name: "",
      zone: "",
      coop: "",
      soy: "",
      tenure: "",
      phone: "",
      email: "",
      fertilizer: "",
      pesticide: "",
      department: "",
      coopPresident: "",
      coopPresidentPhone: "",
      creditOngoing: "",
      sex: "",
      age: null,
      identityPhoto: "",
      currentExploitationIndex: 0,
      exploitations: [emptyExploitation()],
      points: JSON.parse(JSON.stringify(DEFAULT_POINTS)),
      areaHa: null,
      centroid: { lon: null, lat: null },
      harvest: emptyHarvest(),
    };
  }

  function emptyExploitation() {
    return {
      id: null,
      name: "Exploitation SoSoja",
      zone: "",
      points: JSON.parse(JSON.stringify(DEFAULT_POINTS)),
      areaHa: null,
      centroid: { lon: null, lat: null },
    };
  }

  function h(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
  }

  function fmtNumber(value, suffix = "") {
    return value === null || value === undefined || value === "" || Number.isNaN(Number(value)) ? "-" : `${Number(value).toFixed(2)}${suffix}`;
  }

  function fmtDate(value) {
    if (!value) return "-";
    const date = new Date(`${value}T00:00:00`);
    return Number.isNaN(date.getTime()) ? "-" : date.toLocaleDateString("fr-FR");
  }

  function fmtCurrency(value) {
    return value === null || value === undefined || value === "" ? "-" : `${Math.round(Number(value)).toLocaleString("fr-FR")} FCFA`;
  }

  function centroidLabel(producer) {
    const centroid = producerCentroid(producer);
    const lon = centroid && centroid.lon;
    const lat = centroid && centroid.lat;
    return lon === null || lon === undefined || lat === null || lat === undefined ? "-" : `${Number(lon).toFixed(4)}, ${Number(lat).toFixed(4)}`;
  }

  function primaryExploitation(producer) {
    return producer && Array.isArray(producer.exploitations) && producer.exploitations.length ? producer.exploitations[0] : null;
  }

  function selectedDetailExploitation(producer) {
    const exploitations = producer && Array.isArray(producer.exploitations) ? producer.exploitations : [];
    if (!exploitations.length) return null;
    const selected = exploitations.find((item) => item.id === Number(state.detailExploitationId));
    const harvests = Array.isArray(producer.harvests) ? producer.harvests : [];
    const harvestExploitation = harvests.length && exploitations.find((item) => item.id === Number(harvests[0].exploitationId));
    const exploitation = selected || harvestExploitation || exploitations[0];
    state.detailExploitationId = exploitation.id;
    return exploitation;
  }

  function harvestForExploitation(producer, exploitation) {
    if (!producer || !exploitation) return producer && producer.harvest ? producer.harvest : emptyHarvest();
    const harvests = Array.isArray(producer.harvests) ? producer.harvests : [];
    return harvests.find((item) => item.exploitationId === exploitation.id) || emptyHarvest();
  }

  function producerArea(producer) {
    const exploitation = primaryExploitation(producer);
    return exploitation && exploitation.areaHa !== null && exploitation.areaHa !== undefined ? exploitation.areaHa : producer && producer.areaHa;
  }

  function producerCentroid(producer) {
    const exploitation = primaryExploitation(producer);
    return exploitation && exploitation.centroid ? exploitation.centroid : producer && producer.centroid;
  }

  function exploitationUids(producer) {
    return (producer && Array.isArray(producer.exploitations) ? producer.exploitations : [])
      .map((item) => item.uid)
      .filter(Boolean)
      .join(", ");
  }

  function producerPoints(producer) {
    const exploitation = primaryExploitation(producer);
    return exploitation && exploitation.points ? exploitation.points : producer && producer.points;
  }

  function formExploitation() {
    state.form.exploitations = Array.isArray(state.form.exploitations) && state.form.exploitations.length ? state.form.exploitations : [emptyExploitation()];
    const index = Math.min(Math.max(Number(state.form.currentExploitationIndex || 0), 0), state.form.exploitations.length - 1);
    state.form.currentExploitationIndex = index;
    return state.form.exploitations[index];
  }

  function validPoints(points) {
    if (!Array.isArray(points) || points.length < 3) return null;
    const parsed = points
      .filter((point) => point && point.lon !== null && point.lon !== undefined && point.lon !== "" && point.lat !== null && point.lat !== undefined && point.lat !== "")
      .map((point) => ({ lon: Number(point.lon), lat: Number(point.lat) }));
    if (parsed.length < 3) return null;
    return parsed.every((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat)) ? parsed : null;
  }

  function detectedPoints(points) {
    if (!Array.isArray(points)) return [];
    return points
      .filter((point) => point && point.lon !== null && point.lon !== undefined && point.lon !== "" && point.lat !== null && point.lat !== undefined && point.lat !== "")
      .map((point) => ({ lon: Number(point.lon), lat: Number(point.lat) }))
      .filter((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat));
  }

  function centroidOf(points) {
    const projected = projectedPolygon(points);
    if (Math.abs(projected.doubleArea) < 1e-9) {
      return {
        lon: points.reduce((sum, point) => sum + point.lon, 0) / points.length,
        lat: points.reduce((sum, point) => sum + point.lat, 0) / points.length,
      };
    }
    return {
      lon: (projected.centroidX / (6371000 * projected.cosLat0)) * 180 / Math.PI,
      lat: (projected.centroidY / 6371000) * 180 / Math.PI,
    };
  }

  function projectedPolygon(points) {
    const radius = 6371000;
    const lat0 = points.reduce((sum, point) => sum + point.lat, 0) / points.length;
    const cosLat0 = Math.cos(lat0 * Math.PI / 180) || 1;
    const xy = points.map((point) => ({
      x: (point.lon * Math.PI / 180) * radius * cosLat0,
      y: (point.lat * Math.PI / 180) * radius,
    }));
    let doubleArea = 0;
    let centroidX = 0;
    let centroidY = 0;
    for (let i = 0; i < xy.length; i += 1) {
      const next = (i + 1) % xy.length;
      const cross = xy[i].x * xy[next].y - xy[next].x * xy[i].y;
      doubleArea += cross;
      centroidX += (xy[i].x + xy[next].x) * cross;
      centroidY += (xy[i].y + xy[next].y) * cross;
    }
    return {
      doubleArea,
      centroidX: centroidX / (3 * doubleArea),
      centroidY: centroidY / (3 * doubleArea),
      cosLat0,
    };
  }

  function areaHa(points) {
    const projected = projectedPolygon(points);
    if (Math.abs(projected.doubleArea) < 1e-9) {
      return 0;
    }
    return Math.abs(projected.doubleArea) / 2 / 10000;
  }

  function recalculatePlot() {
    const exploitation = formExploitation();
    const points = detectedPoints(exploitation.points);
    if (!points.length) {
      exploitation.areaHa = null;
      exploitation.centroid = { lon: null, lat: null };
      state.form.areaHa = null;
      state.form.centroid = { lon: null, lat: null };
      return;
    }
    const centroid = points.length >= 3 ? centroidOf(points) : points[0];
    exploitation.areaHa = points.length >= 3 ? Number(areaHa(points).toFixed(2)) : null;
    exploitation.centroid = points.length >= 3 ? centroid : { lon: null, lat: null };
    state.form.areaHa = exploitation.areaHa;
    state.form.centroid = exploitation.centroid;
    state.form.zone = state.form.zone || exploitation.zone;
    scheduleOsmZoneLookup(exploitation, centroid);
  }

  function scheduleOsmZoneLookup(exploitation, centroid) {
    if (!centroid || centroid.lon === null || centroid.lat === null) return;
    const key = `${Number(centroid.lat).toFixed(6)},${Number(centroid.lon).toFixed(6)}`;
    if (state.zoneLookupKey === key || state.zoneLookupPendingKey === key) return;
    window.clearTimeout(state.zoneLookupTimer);
    state.zoneLookupPendingKey = key;
    state.zoneLookupTimer = window.setTimeout(() => updateOsmZone(exploitation, centroid, key), 700);
  }

  async function updateOsmZone(exploitation, centroid, key) {
    const situation = await reverseGeocodeOsm(centroid.lat, centroid.lon);
    if (state.zoneLookupPendingKey !== key) return;
    state.zoneLookupPendingKey = "";
    if (!situation) return;
    state.zoneLookupKey = key;
    exploitation.zone = situation;
    state.form.zone = situation;
    state.notice = "Zone géographique récupérée depuis OpenStreetMap.";
    render();
  }

  async function reverseGeocodeOsm(latitude, longitude) {
    const params = new URLSearchParams({
      lat: String(Number(latitude).toFixed(6)),
      lon: String(Number(longitude).toFixed(6)),
    });
    try {
      const response = await fetch(`/soja/api/reverse-geocode?${params.toString()}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return "";
      const data = await response.json();
      return data.situation || "";
    } catch {
      return "";
    }
  }

  function normalizedPointRows(points) {
    const rows = Array.isArray(points) ? points : [];
    while (rows.length < 1) rows.push({ lon: null, lat: null });
    return rows;
  }

  function geolocationErrorMessage(error) {
    if (!error) {
      return "Position GPS indisponible sur ce device.";
    }
    if (error.code === error.PERMISSION_DENIED) {
      return "Autorise l'acces a la localisation du device pour utiliser le GPS.";
    }
    if (error.code === error.POSITION_UNAVAILABLE) {
      return "Le GPS du device ne fournit pas encore de position. Reste a l'exterieur quelques secondes et reessaye.";
    }
    if (error.code === error.TIMEOUT) {
      return "Le GPS n'a pas repondu assez vite. Reste immobile quelques secondes et reessaye.";
    }
    return "Position GPS indisponible sur ce device.";
  }

  function getCurrentDevicePosition() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Geolocation not supported"));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (position) => resolve(position),
        (error) => reject(error),
        {
          enableHighAccuracy: true,
          timeout: 30000,
          maximumAge: 15000,
        },
      );
    });
  }

  function locatePoint(index) {
    const exploitation = formExploitation();
    exploitation.points = normalizedPointRows(exploitation.points);
    if (!Number.isInteger(index) || !exploitation.points[index]) return;
    if (!navigator.geolocation) {
      state.error = "La géolocalisation n'est pas disponible dans ce navigateur.";
      render();
      return;
    }
    state.error = "";
    state.notice = "Recherche du GPS du device...";
    state.locatingPointIndex = index;
    render();
    getCurrentDevicePosition()
      .then((position) => {
        const point = exploitation.points[index] || { lon: null, lat: null };
        point.lon = Number(position.coords.longitude.toFixed(6));
        point.lat = Number(position.coords.latitude.toFixed(6));
        exploitation.points[index] = point;
        state.notice = `Position GPS ajoutée au point ${index + 1}.`;
        recalculatePlot();
      })
      .catch((error) => {
        state.locatingPointIndex = null;
        state.error = geolocationErrorMessage(error);
      })
      .finally(() => {
        state.locatingPointIndex = null;
        render();
      });
  }

  function plotFallbackSvg(rawPoints) {
    const points = validPoints(rawPoints);
    if (!points) return `<p class="map-hint">Saisissez au moins 3 points GPS ou utilisez l'exemple Bénin (Savè).</p>`;
    const minLon = Math.min(...points.map((point) => point.lon));
    const maxLon = Math.max(...points.map((point) => point.lon));
    const minLat = Math.min(...points.map((point) => point.lat));
    const maxLat = Math.max(...points.map((point) => point.lat));
    const lonRange = maxLon - minLon || 0.000001;
    const latRange = maxLat - minLat || 0.000001;
    const svgPoints = points.map((point) => {
      const x = 36 + ((point.lon - minLon) / lonRange) * 328;
      const y = 244 - ((point.lat - minLat) / latRange) * 208;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    const centroid = centroidOf(points);
    const cx = 36 + ((centroid.lon - minLon) / lonRange) * 328;
    const cy = 244 - ((centroid.lat - minLat) / latRange) * 208;
    return `<div class="soja-plot-preview" role="img" aria-label="Contour GPS de l'exploitation">
      <svg viewBox="0 0 400 280" preserveAspectRatio="xMidYMid meet">
        <rect x="0" y="0" width="400" height="280" rx="8"></rect>
        <polygon points="${svgPoints}"></polygon>
        ${points.map((point, index) => {
          const [x, y] = svgPoints.split(" ")[index].split(",");
          return `<g><circle cx="${x}" cy="${y}" r="5"></circle><text x="${Number(x) + 8}" y="${Number(y) - 8}">P${index + 1}</text></g>`;
        }).join("")}
        <circle class="centroid" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="7"></circle>
      </svg>
    </div>`;
  }

  function projectPoint(point, zoom) {
    const sinLat = Math.sin(point.lat * Math.PI / 180);
    const scale = 256 * (2 ** zoom);
    return {
      x: ((point.lon + 180) / 360) * scale,
      y: (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale,
    };
  }

  function plotPreview(producer) {
    const points = validPoints(producerPoints(producer));
    if (!points) return `<p class="map-hint">Saisissez au moins 3 points GPS ou utilisez l'exemple Bénin (Savè).</p>`;
    const zoom = 15;
    const width = 900;
    const height = 430;
    const centroid = centroidOf(points);
    const center = projectPoint(centroid, zoom);
    const topLeft = { x: center.x - width / 2, y: center.y - height / 2 };
    const tileSize = 256;
    const firstTileX = Math.floor(topLeft.x / tileSize);
    const lastTileX = Math.floor((topLeft.x + width) / tileSize);
    const firstTileY = Math.floor(topLeft.y / tileSize);
    const lastTileY = Math.floor((topLeft.y + height) / tileSize);
    const tileMax = 2 ** zoom;
    const tiles = [];
    for (let x = firstTileX; x <= lastTileX; x += 1) {
      for (let y = firstTileY; y <= lastTileY; y += 1) {
        if (y < 0 || y >= tileMax) continue;
        const wrappedX = ((x % tileMax) + tileMax) % tileMax;
        tiles.push(`<img alt="" class="soja-osm-tile" src="https://tile.openstreetmap.org/${zoom}/${wrappedX}/${y}.png" style="left:${Math.round(x * tileSize - topLeft.x)}px;top:${Math.round(y * tileSize - topLeft.y)}px"/>`);
      }
    }
    const projected = points.map((point) => {
      const projectedPoint = projectPoint(point, zoom);
      return {
        x: projectedPoint.x - topLeft.x,
        y: projectedPoint.y - topLeft.y,
      };
    });
    const polygonPoints = projected.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    const centerPoint = projectPoint(centroid, zoom);
    const centerX = centerPoint.x - topLeft.x;
    const centerY = centerPoint.y - topLeft.y;
    return `<div class="leaflet-map soja-osm-static" role="img" aria-label="Carte OpenStreetMap de l'exploitation">
      <div class="soja-osm-tiles">${tiles.join("")}</div>
      <svg class="soja-osm-overlay" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        <polygon points="${polygonPoints}"></polygon>
        ${projected.map((point, index) => `<g><circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="7"></circle><text x="${(point.x + 10).toFixed(1)}" y="${(point.y - 10).toFixed(1)}">P${index + 1}</text></g>`).join("")}
        <circle class="centroid" cx="${centerX.toFixed(1)}" cy="${centerY.toFixed(1)}" r="8"></circle>
      </svg>
      <div class="soja-osm-attribution">© OpenStreetMap</div>
    </div>`;
  }

  function stockLabel(harvest) {
    if (!harvest || !harvest.stock || harvest.stock.qtyT === null || harvest.stock.qtyT === undefined) return "-";
    return `${harvest.stock.type === "total" ? "Total" : "Partiel"} - ${Number(harvest.stock.qtyT).toFixed(2)} t`;
  }

  function shareLabel(status) {
    return { private: "Privé", partners: "Partenaires", cooperative: "Coopérative", factory: "Usine", bank: "Banque" }[status || "private"] || "Partagé";
  }

  function servicesLabel(services) {
    if (!services) return "-";
    return [
      services.drone ? "Drone" : "",
      services.soil ? "Sol" : "",
      services.training ? "Coaching" : "",
      services.finance ? "Financement" : "",
    ].filter(Boolean).join(", ") || "-";
  }

  function selectedProducer() {
    return state.producers.find((producer) => producer.id === Number(state.selectedId)) || null;
  }

  function canView(view) {
    return state.session && Array.isArray(state.session.views) && state.session.views.includes(view);
  }

  function defaultView() {
    if (!state.session) return "list";
    if (state.session.role === "producer") return state.producers.length ? "details" : "entry";
    return state.session.views[0] || "list";
  }

  function campaigns() {
    return [...new Set(state.producers.map((producer) => producer.harvest && producer.harvest.campaign).filter(Boolean))].sort();
  }

  function filteredProducers() {
    const query = state.query.trim().toLowerCase();
    return state.producers.filter((producer) => {
      const matchesCampaign = !state.campaign || (producer.harvest && producer.harvest.campaign === state.campaign);
      return matchesCampaign && (!query || JSON.stringify(producer).toLowerCase().includes(query));
    });
  }

  function producerRows(rows) {
    if (!rows.length) return `<tr><td class="empty" colspan="19">Aucun producteur.</td></tr>`;
    return rows.map((producer) => {
      const harvest = producer.harvest || {};
      return `<tr class="clickable-row" data-action="details" data-id="${producer.id}">
        <td><strong>${h(producer.name)}</strong><small>${fmtDate((producer.createdAt || "").slice(0, 10))}</small></td>
        <td class="mono">${h(exploitationUids(producer) || "-")}</td>
        <td>${h(producer.zone || "-")}</td>
        <td>${h(producer.coop || "-")}</td>
        <td>${h(producer.soy || "-")}</td>
        <td>${h(producer.tenure || "-")}</td>
        <td>${h(producer.phone || "-")}</td>
        <td>${h(producer.email || "-")}</td>
        <td>${fmtNumber(producerArea(producer), " ha")}</td>
        <td class="mono">${centroidLabel(producer)}</td>
        <td>${h(harvest.campaign || "-")}</td>
        <td>${fmtDate(harvest.seedDate)}</td>
        <td>${fmtDate(harvest.harvestForecastDate)}</td>
        <td>${fmtDate(harvest.harvestActualDate)}</td>
        <td>${fmtNumber(harvest.forecastT, " t")}</td>
        <td>${fmtNumber(harvest.actualT, " t")}</td>
        <td><span class="badge ${harvest.shareStatus === "private" ? "private" : ""}">${shareLabel(harvest.shareStatus)}</span></td>
        <td>${servicesLabel(harvest.services)}</td>
        <td class="row-actions">
          ${canView("entry") ? `<button class="btn compact light" data-action="edit" data-id="${producer.id}" type="button">Modifier</button>` : ""}
          ${state.session && state.session.role === "manager" ? `<button class="btn compact danger" data-action="delete" data-id="${producer.id}" type="button">Suppr.</button>` : ""}
        </td>
      </tr>`;
    }).join("");
  }

  function header(active) {
    const tabs = [
      ["entry", "Saisie"],
      ["list", "Liste"],
      ["details", "Détails"],
      ["seed", "Semence"],
      ["harvest", "Récoltes"],
      ["cooperative", "Coopérative"],
      ["factory", "Usine"],
      ["bank", "Banque"],
    ].filter(([view]) => canView(view));
    const connectivityLabel = state.isOnline ? "En ligne" : "Hors ligne";
    const connectivityClass = state.isOnline ? "success" : "warning";
    const pendingLabel = state.pendingWrites ? `<span class="pill info">${state.pendingWrites} attente${state.pendingWrites > 1 ? "s" : ""}</span>` : "";
    const syncLabel = state.syncingQueue ? `<span class="pill info">Synchronisation</span>` : "";
    const syncTime = state.lastSyncAt ? `<span class="pill">${new Date(state.lastSyncAt).toLocaleString("fr-FR")}</span>` : "";
    const syncDisabled = state.isOnline ? "" : " disabled aria-disabled=\"true\"";
    const syncTitle = state.isOnline ? "Synchroniser la donnée locale" : "Synchronisation indisponible hors ligne";
    return `<header class="mc-header"><div class="mc-top"><div class="mc-title">SoSoja</div><div class="mc-actions"><span class="pill ${connectivityClass}">${connectivityLabel}</span>${pendingLabel}${syncLabel}${syncTime}<button class="icon-button" data-action="reload" type="button" title="${syncTitle}"${syncDisabled}>${uploadIcon()}</button></div></div>
      <nav class="mc-tabs">${tabs.map(([view, label]) => `<a class="mc-tab ${active === view ? "active" : ""}" href="#" data-view="${view}">${label}</a>`).join("")}</nav></header>`;
  }

  function alerts() {
    const offlineNotice = !state.isOnline
      ? `<p class="alert warning">Mode hors ligne actif. Les modifications sont stockées localement puis synchronisées au retour du réseau.</p>`
      : "";
    const syncNotice = state.pendingWrites
      ? `<p class="alert warning">${state.pendingWrites} modification${state.pendingWrites > 1 ? "s" : ""} en attente de synchronisation.</p>`
      : "";
    const cachedNotice = !state.isOnline && !state.producers.length
      ? `<p class="alert warning">Aucune donnée locale trouvée. Ouvre l'app au moins une fois en ligne avant de couper la connexion.</p>`
      : "";
    return `${offlineNotice}${syncNotice}${cachedNotice}${state.error ? `<p class="alert error">${h(state.error)}</p>` : ""}${state.notice ? `<p class="alert success">${h(state.notice)}</p>` : ""}`;
  }

  function listView() {
    const rows = filteredProducers();
    return `${header("list")}<main class="mc-main">
      <section class="hero"><div><h1>Liste producteurs</h1><p>Vue consolidée : producteur, semence et récolte. Les données sont persistées dans Odoo via le module SoSoja Management.</p></div><div class="meta"><span class="pill info">Vue d'ensemble</span><span class="pill info">Filtre campagne</span><span class="pill success">Odoo</span></div></section>
      <section class="toolbar"><div class="field-group"><input class="control" data-field="query" type="search" placeholder="Rechercher" value="${h(state.query)}"/><select class="control small" data-field="campaign"><option value="">Toutes campagnes</option>${campaigns().map((campaign) => `<option ${campaign === state.campaign ? "selected" : ""}>${h(campaign)}</option>`).join("")}</select></div><div class="actions"><span class="count">${rows.length} / ${state.producers.length}</span><button class="btn light" data-action="export" type="button">Exporter JSON</button><button class="btn primary" data-view="entry" type="button">Nouveau producteur</button></div></section>
      ${alerts()}
      <section class="tablewrap"><table><thead><tr><th>Producteur</th><th>UUID exploitations</th><th>Zone</th><th>Coopérative</th><th>Type</th><th>Titre</th><th>Tel</th><th>Email</th><th>Surface</th><th>Centroïde</th><th>Campagne</th><th>Date semence</th><th>Récolte prévue</th><th>Récolte effective</th><th>Qté prévue</th><th>Qté effective</th><th>Partage</th><th>Services</th><th></th></tr></thead><tbody>${producerRows(rows)}</tbody></table></section>
    </main>`;
  }

  function detailOperation(exploitation, collection, stateKey) {
    const rows = exploitation && exploitation[collection] ? exploitation[collection] : [];
    const selectedId = Number(state[stateKey]) || (rows[0] && rows[0].id);
    const options = rows.map((item) => {
      const name = item[collection === "storageInfos" ? "cooperativeName" : collection === "treatmentInfos" ? "factoryName" : "bankName"] || "-";
      const date = item.date ? ` - ${fmtDate(item.date)}` : "";
      return `<option value="${item.id}" ${item.id === selectedId ? "selected" : ""}>${h(`${name}${date} - ligne #${item.id}`)}</option>`;
    }).join("");
    const selected = rows.find((item) => item.id === selectedId) || null;
    return { rows, selected, options, selectedId };
  }

  function detailTopic(producer, exploitation) {
    const harvest = harvestForExploitation(producer, exploitation);
    const storage = detailOperation(exploitation, "storageInfos", "detailCooperativeId");
    const treatment = detailOperation(exploitation, "treatmentInfos", "detailFactoryId");
    const bank = detailOperation(exploitation, "bankInfos", "detailBankId");
    return `<section class="panel-section"><h2>Données semence et récolte</h2><div class="details-topic-grid">
      <section class="details-topic"><h3>Semence</h3><div class="readonly-grid compact"><div><span>Campagne</span><strong>${h(harvest.campaign || "-")}</strong></div><div><span>Date semence</span><strong>${fmtDate(harvest.seedDate)}</strong></div><div><span>Date récolte prévue</span><strong>${fmtDate(harvest.harvestForecastDate)}</strong></div><div><span>Qté prévue</span><strong>${fmtNumber(harvest.forecastT, " t")}</strong></div></div></section>
      <section class="details-topic"><h3>Récolte</h3><div class="readonly-grid compact"><div><span>Date récolte effective</span><strong>${fmtDate(harvest.harvestActualDate)}</strong></div><div><span>Qté effective</span><strong>${fmtNumber(harvest.actualT, " t")}</strong></div><div><span>Rendement</span><strong>${fmtNumber(harvest.yieldTha, " t/ha")}</strong></div></div></section>
      <section class="details-topic"><h3>Stockage coopérative</h3>${storage.rows.length ? `<label>Coopérative<select class="control" data-detail-operation="cooperative">${storage.options}</select></label>${storage.selected ? `<div class="readonly-grid compact"><div><span>Stockage</span><strong>${h(storage.selected.type || "-")}</strong></div><div><span>Quantité</span><strong>${fmtNumber(storage.selected.quantityT, " t")}</strong></div><div><span>Date stockage</span><strong>${fmtDate(storage.selected.date)}</strong></div><div><span>Note stockage</span><strong>${h(storage.selected.note || "-")}</strong></div></div>` : ""}` : `<p class="empty">Aucune information de stockage.</p>`}</section>
      <section class="details-topic"><h3>Traitement usine</h3>${treatment.rows.length ? `<label>Usine<select class="control" data-detail-operation="factory">${treatment.options}</select></label>${treatment.selected ? `<div class="readonly-grid compact"><div><span>Décorticage</span><strong>${treatment.selected.dehull ? "Oui" : "Non"}</strong></div><div><span>Broyage</span><strong>${treatment.selected.grind ? "Oui" : "Non"}</strong></div><div><span>Stockage source</span><strong>${h(treatment.selected.storageInfoLabel || "-")}</strong></div><div><span>Date traitement</span><strong>${fmtDate(treatment.selected.date)}</strong></div><div><span>Note traitement</span><strong>${h(treatment.selected.note || "-")}</strong></div></div>` : ""}` : `<p class="empty">Aucune information de traitement.</p>`}</section>
      <section class="details-topic"><h3>Dossier bancaire</h3>${bank.rows.length ? `<label>Banque<select class="control" data-detail-operation="bank">${bank.options}</select></label>${bank.selected ? `<div class="readonly-grid compact"><div><span>Emprunteur</span><strong>${h(bank.selected.borrowerName || "-")}</strong></div><div><span>Montant demandé</span><strong>${fmtCurrency(bank.selected.requestedAmount)}</strong></div><div><span>Montant approuvé</span><strong>${fmtCurrency(bank.selected.approvedAmount)}</strong></div><div><span>Statut</span><strong>${h(bank.selected.status || "-")}</strong></div></div>` : ""}` : `<p class="empty">Aucune information bancaire.</p>`}</section>
      <section class="details-topic"><h3>Partage et services</h3><div class="readonly-grid compact"><div><span>Partage</span><strong>${shareLabel(harvest.shareStatus)}</strong></div><div><span>Services</span><strong>${servicesLabel(harvest.services)}</strong></div></div></section>
    </div></section>`;
  }

  function detailsView() {
    const producer = selectedProducer();
    if (!producer) return `${header("details")}<main class="mc-main"><section class="panel-section"><h2>Aucun producteur sélectionné</h2><p class="muted-line">Retourne à la liste et clique sur une ligne.</p><button class="btn primary" data-view="list" type="button">Retour à la liste</button></section></main>`;
    const displayedExploitation = selectedDetailExploitation(producer);
    const displayedPoints = displayedExploitation && displayedExploitation.points ? displayedExploitation.points : [];
    return `${header("details")}<main class="mc-main">
      <section class="hero"><div><h1>Détails producteur</h1><p>Consultez les informations du producteur, la parcelle et les données associées.</p></div><div class="meta"><span class="pill info">${h(producer.zone || "-")}</span><span class="pill info">Identité</span><span class="pill info">Parcelle</span><span class="pill success">Odoo</span></div></section>
      <section class="toolbar"><div class="actions">${canView("list") ? `<button class="btn light" data-view="list" type="button">Retour liste</button>` : ""}</div><div class="actions">${canView("entry") ? `<button class="btn light" data-action="edit" data-id="${producer.id}" type="button">Éditer</button>` : ""}${canView("seed") ? `<button class="btn light" data-view="seed" data-id="${producer.id}" type="button">Semence</button>` : ""}${canView("harvest") ? `<button class="btn light" data-view="harvest" data-id="${producer.id}" type="button">Récolte</button>` : ""}${state.session && state.session.role === "manager" ? `<button class="btn danger" data-action="delete" data-id="${producer.id}" type="button">Supprimer</button>` : ""}</div></section>
      ${alerts()}
      <section class="panel-section"><div class="section-head"><div><h2>Choix de l'exploitation</h2><p>Les données de semence, de récolte et la carte correspondent à l'exploitation sélectionnée.</p></div></div><label>Exploitation affichée<select class="control" data-detail-exploitation="1">${(producer.exploitations || []).map((item) => `<option value="${item.id}" ${displayedExploitation && displayedExploitation.id === item.id ? "selected" : ""}>${h(item.name)} - ${fmtNumber(item.areaHa, " ha")}</option>`).join("")}</select></label></section>
      <section class="details-layout"><section class="panel-section"><div class="section-head"><div><h2>Pièce d'identité</h2><p>Photo enregistrée dans Odoo.</p></div></div><div class="photo-preview details-photo">${producer.identityPhoto ? `<img src="${h(producer.identityPhoto)}" alt="Photo identité"/>` : "<span>Aucune photo.</span>"}</div></section>
      <section class="panel-section"><h2>Informations producteur</h2><div class="readonly-grid">
        ${readonly("Producteur", producer.name)}${readonly("UUID exploitation affichée", displayedExploitation && displayedExploitation.uid, "mono")}${readonly("Zone", producer.zone)}${readonly("Coopérative", producer.coop)}${readonly("Type de soja", producer.soy)}${readonly("Titre de propriété", producer.tenure)}${readonly("Tel", producer.phone)}${readonly("Email", producer.email)}${readonly("Engrais", producer.fertilizer)}${readonly("Herbicides", producer.pesticide)}${readonly("Exploitations", (producer.exploitations || []).length || 0)}${readonly("Surface totale", fmtNumber(producer.areaHa, " ha"))}${readonly("Exploitation affichée", displayedExploitation && displayedExploitation.name)}${readonly("Centroïde affiché", displayedExploitation ? centroidLabel(displayedExploitation) : "-", "mono")}${readonly("Département", producer.department)}${readonly("Président coopérative", producer.coopPresident)}${readonly("Contact président", producer.coopPresidentPhone)}${readonly("Crédit en cours", producer.creditOngoing)}${readonly("Sexe", producer.sex)}${readonly("Âge", producer.age || "-")}
      </div></section></section>
      ${detailTopic(producer, displayedExploitation)}
      <section class="panel-section"><h2>Exploitations</h2><div class="tablewrap compact-table"><table><thead><tr><th>Exploitation</th><th>UUID</th><th>Zone</th><th>Surface</th><th>Centroïde</th></tr></thead><tbody>${(producer.exploitations || []).map((item) => `<tr class="clickable-row ${displayedExploitation && displayedExploitation.id === item.id ? "selected-row" : ""}" data-action="selectExploitation" data-id="${item.id}"><td><strong>${h(item.name || "-")}</strong></td><td class="mono">${h(item.uid || "-")}</td><td>${h(item.zone || "-")}</td><td>${fmtNumber(item.areaHa, " ha")}</td><td class="mono">${centroidLabel(item)}</td></tr>`).join("") || `<tr><td class="empty" colspan="5">Aucune exploitation.</td></tr>`}</tbody></table></div></section>
      <section class="panel-section"><h2>Délimitation de l'exploitation affichée</h2><div class="tablewrap compact-table"><table><thead><tr><th>Point</th><th>Longitude</th><th>Latitude</th></tr></thead><tbody>${displayedPoints.map((point, index) => `<tr><td><strong>P${index + 1}</strong></td><td class="mono">${point.lon ?? "-"}</td><td class="mono">${point.lat ?? "-"}</td></tr>`).join("") || `<tr><td class="empty" colspan="3">Aucune coordonnée GPS complète.</td></tr>`}</tbody></table></div></section>
      <section class="plot-grid"><div class="metric"><span>Surface affichée</span><strong>${fmtNumber(displayedExploitation && displayedExploitation.areaHa, " ha")}</strong></div><div class="metric"><span>Zone</span><strong>${h((displayedExploitation && displayedExploitation.zone) || producer.zone || "-")}</strong></div><div class="metric"><span>Centroïde</span><strong class="mono">${displayedExploitation ? centroidLabel(displayedExploitation) : "-"}</strong></div><div class="map-panel">${displayedExploitation ? plotPreview(displayedExploitation) : plotFallbackSvg([])}</div></section>
    </main>`;
  }

  function readonly(label, value, cls = "") {
    return `<div><span>${h(label)}</span><strong class="${cls}">${h(value || "-")}</strong></div>`;
  }

  function input(label, key, type = "text", required = false) {
    return `<label class="${required ? "required" : ""}">${label}<input class="control" ${required ? "required" : ""} type="${type}" data-form="${key}" value="${h(state.form[key] ?? "")}"/></label>`;
  }

  function select(label, key, options, required = false) {
    return `<label class="${required ? "required" : ""}">${label}<select class="control" data-form="${key}"><option value="">-</option>${options.map((option) => `<option ${state.form[key] === option ? "selected" : ""}>${h(option)}</option>`).join("")}</select></label>`;
  }

  function entryView() {
    const exploitation = formExploitation();
    return `${header("entry")}<main class="mc-main"><section class="hero"><div><h1>Enregistrement données producteur</h1><p>Enregistrez un producteur et sa parcelle. Données prêtes pour le suivi semence et récolte dans Odoo.</p></div><div class="meta"><span class="pill info">Opérateur terrain</span><span class="pill info">Contrôle qualité</span><span class="pill success">Odoo</span></div></section>${alerts()}
      <form class="entry-shell" data-action="save"><div class="savebar"><button class="btn light" data-view="list" type="button">Retour liste</button><button class="btn primary" type="submit">${state.saving ? "Enregistrement..." : "Enregistrer"}</button></div>
      <section class="panel-section"><h2>Informations producteur</h2><div class="form-grid">
        ${input("Identité du producteur", "name", "text", true)}${select("Type de soja cultivé", "soy", ["Conventionnel", "Bio"], true)}${select("Titre de propriété / location", "tenure", ["Propriété", "Location", "Concession", "Autre"], true)}${input("Coopérative", "coop", "text", true)}
        ${input("Département", "department")}${input("Président de la coopérative", "coopPresident")}${input("Téléphone président", "coopPresidentPhone")}${select("Crédit en cours ?", "creditOngoing", ["Oui", "Non"])}${select("Sexe", "sex", ["F", "M"])}${input("Âge du producteur", "age", "number")}${input("Téléphone producteur", "phone", "text", true)}${input("Email", "email", "email", true)}${select("Types d'engrais utilisés", "fertilizer", ["Semence", "K2SO4", "KCL", "Inoculum", "Aucun"])}${select("Herbicides", "pesticide", ["Herbicide total", "Herbicide sélectif", "Aucun"])}
      </div></section>
      <section class="panel-section"><div class="section-head"><div><h2>Exploitations</h2><p>Chaque exploitation est rattachée à ce contact producteur.</p></div><button class="btn light" data-action="addExploitation" type="button">Ajouter exploitation</button></div><div class="field-group"><select class="control" data-form="currentExploitationIndex">${state.form.exploitations.map((item, index) => `<option value="${index}" ${index === state.form.currentExploitationIndex ? "selected" : ""}>${h(item.name || `Exploitation ${index + 1}`)}</option>`).join("")}</select><button class="btn danger" data-action="removeExploitation" type="button">Supprimer exploitation</button></div><div class="form-grid"><label>Nom exploitation<input class="control" data-exploitation-field="name" value="${h(exploitation.name || "")}"/></label><label>Zone exploitation<input class="control" data-exploitation-field="zone" value="${h(exploitation.zone || "")}"/></label><label>Surface (ha)<input class="control" type="number" data-exploitation-field="areaHa" value="${h(exploitation.areaHa ?? "")}"/></label></div><div class="section-head points-head"><div><h3>Points GPS</h3><p>Ajoutez autant de points que nécessaire. Trois points complets minimum sont requis pour calculer le contour.</p></div><button class="btn light" data-action="addPoint" type="button">Ajouter point</button></div><div class="points-grid">${normalizedPointRows(exploitation.points).map((point, i) => `<label>Point ${i + 1}<span><input class="control" type="number" step="0.000001" placeholder="Longitude" data-point="${i}" data-axis="lon" value="${h(point.lon ?? "")}"/><input class="control" type="number" step="0.000001" placeholder="Latitude" data-point="${i}" data-axis="lat" value="${h(point.lat ?? "")}"/><button class="btn compact light point-locate" data-action="locatePoint" data-point-index="${i}" type="button" ${state.locatingPointIndex === i ? "disabled" : ""}>${state.locatingPointIndex === i ? "..." : "Lire le GPS du device"}</button><button class="btn compact danger point-remove" data-action="removePoint" data-point-index="${i}" type="button" ${normalizedPointRows(exploitation.points).length <= 3 ? "disabled" : ""}>Supprimer</button></span></label>`).join("")}</div><button class="btn light" data-action="useSaveExample" type="button">Utiliser l'exemple Bénin (Savè)</button></section>
      <section class="plot-grid"><div class="metric"><span>Surface (ha)</span><strong>${fmtNumber(exploitation.areaHa)}</strong></div><div class="metric"><span>Zone géographique</span><strong>${h(exploitation.zone || "-")}</strong></div><div class="metric"><span>Centroïde</span><strong class="mono">${centroidLabel(exploitation)}</strong></div><div class="map-panel">${plotPreview(exploitation)}</div></section>
      </form></main>`;
  }

  function seedHarvestView(kind) {
    const producer = selectedProducer() || state.producers[0];
    if (producer && !state.selectedId) state.selectedId = producer.id;
    const form = kind === "seed" ? state.seedForm : state.harvestForm;
    const title = kind === "seed" ? "Semence" : "Récolte";
    const subtitle = kind === "seed" ? "Saisissez les informations de semence et préparez le suivi de campagne." : "Saisissez les résultats de récolte et mettez à jour quantités et rendements.";
    const exploitations = (producer && producer.exploitations) || [];
    const selectedExploitation = exploitations.find((item) => item.id === Number(form.exploitationId)) || exploitations[0] || null;
    if (selectedExploitation && !form.exploitationId) form.exploitationId = selectedExploitation.id;
    const yieldKey = kind === "seed" ? "yieldTha" : "actualYieldTha";
    const estimate = selectedExploitation && Number(selectedExploitation.areaHa) && Number(form[yieldKey]) ? (Number(selectedExploitation.areaHa) * Number(form[yieldKey])).toFixed(2) : "";
    return `${header(kind)}<main class="mc-main"><section class="hero"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="meta"><span class="pill info">Mode exploitant</span><span class="pill info">Campagne</span><span class="pill success">Odoo</span></div></section>${alerts()}
      <section class="seed-layout"><section class="panel-section"><div class="section-head"><div><h2>Sélection exploitation</h2><p>${state.producers.length} producteurs</p></div><button class="btn light" data-view="list" type="button">Retour liste</button></div>
      <label>Choisir un producteur<select class="control" data-field="selectedId">${state.producers.map((item) => `<option value="${item.id}" ${Number(state.selectedId) === item.id ? "selected" : ""}>${h(item.name)} - ${h(item.zone || "-")}</option>`).join("")}</select></label>
      <label>Choisir une exploitation<select class="control" data-harvest="exploitationId">${exploitations.map((item) => `<option value="${item.id}" ${Number(form.exploitationId) === item.id ? "selected" : ""}>${h(item.name)} - ${fmtNumber(item.areaHa, " ha")}</option>`).join("")}</select></label>
      <div class="seed-metrics"><div><span>Surface</span><strong>${fmtNumber(selectedExploitation && selectedExploitation.areaHa, " ha")}</strong></div><div><span>Zone</span><strong>${h((selectedExploitation && selectedExploitation.zone) || "-")}</strong></div></div>
      <h3>Propositions d'amélioration</h3><ul class="recommendations"><li>Regrouper les achats d'intrants via la coopérative.</li><li>Optimiser densité de semis et plan de fertilisation.</li><li>Enregistrer toutes les opérations culturales pour la traçabilité.</li></ul>
      <div class="service-box"><strong>Services additionnels</strong><p>Coche ce qui est pertinent.</p>${["drone:Cartographie drone / GPS", "soil:Analyse de sol + plan de fertilisation", "training:Coaching technique", "finance:Accompagnement financement"].map((row) => { const [key, label] = row.split(":"); return `<label><input type="checkbox" data-harvest-service="${key}" ${form.services[key] ? "checked" : ""}/> ${label}</label>`; }).join("")}</div></section>
      <section class="panel-section"><h2>${kind === "seed" ? "Enregistrer une récolte prévisionnelle" : "Enregistrer une récolte effective"}</h2><div class="form-grid seed-form">
        <label>Campagne<input class="control" data-harvest="campaign" value="${h(form.campaign || "")}"/></label>
        ${kind === "seed" ? `<label>Date semence<input class="control" type="date" data-harvest="seedDate" value="${h(form.seedDate || "")}"/></label><label>Date récolte prévue<input class="control" type="date" data-harvest="harvestForecastDate" value="${h(form.harvestForecastDate || "")}"/></label>` : `<label>Date récolte effective<input class="control" type="date" data-harvest="harvestActualDate" value="${h(form.harvestActualDate || "")}"/></label>`}
        <label>Rendement ${kind === "seed" ? "estimé" : "effectif"} (t/ha)<input class="control" type="number" step="0.01" data-harvest="${yieldKey}" value="${h(form[yieldKey] ?? "")}"/></label>
        <label>Quantité ${kind === "seed" ? "prévue" : "effective"} (tonnes)<input class="control" value="${h(kind === "seed" ? estimate : estimate)}" disabled/></label>
        <label>Statut de partage<select class="control" data-harvest="shareStatus">${["private", "cooperative", "factory", "bank", "partners"].map((status) => `<option value="${status}" ${form.shareStatus === status ? "selected" : ""}>${shareLabel(status)}</option>`).join("")}</select></label>
      </div><div class="actions seed-actions"><button class="btn primary" data-action="${kind === "seed" ? "saveSeed" : "saveHarvest"}" type="button">Enregistrer</button><button class="btn danger" data-action="${kind === "seed" ? "deleteSeed" : "deleteHarvest"}" type="button">Supprimer</button></div></section></section></main>`;
  }

  function partnerRows(kind) {
    const query = state.query.trim().toLowerCase();
    return state.producers.filter((producer) => {
      const status = producer.harvest && producer.harvest.shareStatus;
      const matchesRole =
        kind === "cooperative" ? status === "partners" || status === "cooperative" :
        kind === "factory" ? status === "partners" || status === "factory" :
        status === "bank" || status === "partners";
      const matchesCampaign = !state.campaign || (producer.harvest && producer.harvest.campaign === state.campaign);
      return matchesRole && matchesCampaign && (!query || JSON.stringify(producer).toLowerCase().includes(query));
    });
  }

  function sumRows(rows, getter) {
    return rows.reduce((sum, producer) => sum + Number(getter(producer) || 0), 0);
  }

  function stockQty(producer) {
    return producer.harvest && producer.harvest.stock ? producer.harvest.stock.qtyT : null;
  }

  function untreatedQty(producer) {
    const harvest = producer.harvest || {};
    return Math.max(Number(harvest.actualT || harvest.forecastT || 0) - Number(stockQty(producer) || 0), 0);
  }

  function feedableQty(producer) {
    return Number(stockQty(producer) || (producer.harvest && producer.harvest.actualT) || 0);
  }

  function productionCost(producer) {
    return Number((producer.harvest && producer.harvest.forecastT) || 0) * 1000 * 200;
  }

  function selectedPartner(rows) {
    const selected = rows.find((producer) => producer.id === Number(state.selectedId)) || rows[0] || null;
    if (selected && Number(state.selectedId) !== selected.id) {
      state.selectedId = selected.id;
      state.partnerForm = JSON.parse(JSON.stringify(selected.harvest || emptyHarvest()));
    }
    return selected;
  }

  function partnerSidebar(kind) {
    const label = { cooperative: "Coopérative", factory: "Usine", bank: "Banque" }[kind];
    const cls = kind === "cooperative" ? "coop" : kind;
    const items = [
      ["entry", "Saisie", "›"],
      ["list", "Producteurs", "›"],
      ["details", "Détails", "›"],
      ["seed", "Semence", "›"],
      ["harvest", "Récoltes", "›"],
      ["cooperative", "Coopérative", "P2"],
      ["factory", "Usine", "P2"],
      ["bank", "Banque", "P2"],
    ].filter(([view]) => canView(view));
    return `<aside class="${cls}-sidebar">
      <div class="${cls}-logo"><span></span> SoSoja</div>
      <div class="${cls}-user"><div class="${cls}-avatar"></div><div><strong>Compte Partenaire</strong><small>${label}</small></div></div>
      <nav class="${cls}-nav">${items.map(([view, text, suffix]) => view === "cooperative"
        ? `<div>Phase 2</div><a class="${kind === view ? "active" : ""}" href="#" data-view="${view}">${text} <span>${suffix}</span></a>`
        : `<a class="${kind === view ? "active" : ""}" href="#" data-view="${view}">${text} <span>${suffix}</span></a>`).join("")}</nav>
    </aside>`;
  }

  function partnerTopbar(kind) {
    const cls = kind === "cooperative" ? "coop" : kind;
    const syncDisabled = state.isOnline ? "" : " disabled aria-disabled=\"true\"";
    const syncTitle = state.isOnline ? "Synchroniser la donnée locale" : "Synchronisation indisponible hors ligne";
    return `<section class="${cls}-topbar">
      <div class="${cls}-top-left">
        <button class="icon-button" type="button">≡</button>
        <strong>Dashboard</strong>
        <div class="${cls}-search"><span>🔎</span><input data-field="query" placeholder="Search (zone, producteur, volume...)" value="${h(state.query)}" /></div>
        <select class="control small" data-field="campaign"><option value="">Toutes campagnes</option>${campaigns().map((campaign) => `<option value="${h(campaign)}" ${campaign === state.campaign ? "selected" : ""}>${h(campaign)}</option>`).join("")}</select>
      </div>
      <div class="actions">
        <button class="btn light with-icon" data-action="reload" type="button" title="${syncTitle}"${syncDisabled}>${uploadIcon()}<span>Synchroniser la donnée locale</span></button>
        <button class="btn primary" data-action="export" type="button">Exporter</button>
        <button class="icon-button" type="button" title="Messages">✉</button>
        <button class="icon-button" type="button" title="Notifications">🔔</button>
      </div>
    </section>`;
  }

  function coopView() {
    const rows = partnerRows("cooperative");
    const selected = selectedPartner(rows);
    const form = state.partnerForm || JSON.parse(JSON.stringify((selected && selected.harvest) || emptyHarvest()));
    return `<main class="coop-app soja-odoo-partner">${partnerSidebar("cooperative")}
      <section class="coop-main soja-odoo-full">
        <section class="coop-hero"><h1>Vue coopérative</h1><p>Validez les prévisionnels partagés et sécurisez la chaîne via stockage total ou partiel.</p><div class="meta"><span class="pill info">Coopérative</span><span class="pill info">Stockage</span><span class="pill success">Odoo</span></div></section>
        ${partnerTopbar("cooperative")}${alerts()}
        <section class="coop-kpis"><div class="coop-kpi"><span>Volume total entrepôt:</span><strong>${fmtNumber(sumRows(rows, (p) => p.harvest && p.harvest.forecastT), " t")}</strong></div><div class="coop-kpi"><span>Volume actuel stocké dans entrepôt</span><strong>${fmtNumber(sumRows(rows, stockQty), " t")}</strong></div><div class="coop-kpi"><span>Producteurs couverts</span><strong>${rows.length}</strong><small>Selon le rôle</small></div></section>
        <section class="coop-dashboard">
          <section class="coop-card"><div class="coop-card-head"><div><h2>Prévisionnel partagé partenaires</h2><p>Filtre + export. Clique une ligne pour saisir le stockage.</p></div><span class="pill success">Partagé</span></div>
            <div class="tablewrap coop-tablewrap"><table><thead><tr><th>Producteur</th><th>Zone</th><th>Téléphone</th><th>Email</th><th>Surface</th><th>Campagne</th><th>Date semence</th><th>Récolte prévue</th><th>Récolte effective</th><th>Qté prévue</th><th>Qté effective</th><th>Stockage</th><th>Stocké le</th><th>Note stockage</th><th>Quantité non traitée</th><th>Rendement</th><th>Partage</th><th></th></tr></thead><tbody>${rows.map((producer) => `<tr class="clickable-row ${selected && selected.id === producer.id ? "selected-row" : ""}" data-action="details" data-id="${producer.id}"><td><strong>${h(producer.name)}</strong></td><td>${h(producer.zone || "-")}</td><td>${h(producer.phone || "-")}</td><td>${h(producer.email || "-")}</td><td>${fmtNumber(producerArea(producer), " ha")}</td><td>${h((producer.harvest && producer.harvest.campaign) || "-")}</td><td>${fmtDate(producer.harvest && producer.harvest.seedDate)}</td><td>${fmtDate(producer.harvest && producer.harvest.harvestForecastDate)}</td><td>${fmtDate(producer.harvest && producer.harvest.harvestActualDate)}</td><td>${fmtNumber(producer.harvest && producer.harvest.forecastT, " t")}</td><td>${fmtNumber(producer.harvest && producer.harvest.actualT, " t")}</td><td>${stockLabel(producer.harvest)}</td><td>${fmtDate(producer.harvest && producer.harvest.stock && producer.harvest.stock.date)}</td><td>${h((producer.harvest && producer.harvest.stock && producer.harvest.stock.note) || "-")}</td><td>${fmtNumber(untreatedQty(producer), " t")}</td><td>${fmtNumber(producer.harvest && producer.harvest.yieldTha)}</td><td><span class="badge">${shareLabel(producer.harvest && producer.harvest.shareStatus)}</span></td><td><button class="btn compact light" data-action="selectPartner" data-id="${producer.id}" type="button">Stockage</button></td></tr>`).join("") || `<tr><td class="empty" colspan="18">Aucune donnée partagée.</td></tr>`}</tbody></table></div>
          </section>
          <section class="coop-card"><div class="coop-card-head"><div><h2>Stockage</h2><p>Choisis d'abord l'exploitation concernée avant d'enregistrer le stockage.</p></div><span class="pill info">${h((selected && selected.name) || "Sélectionne une ligne")}</span></div>${selected ? `<label>Exploitation à stocker<select class="control" data-partner-exploitation="1">${(selected.exploitations || []).map((item) => `<option value="${item.id}" ${Number(form.exploitationId) === item.id ? "selected" : ""}>${h(item.name)} - ${fmtNumber(item.areaHa, " ha")}</option>`).join("")}</select></label>${partnerEditor("cooperative", form)}<div class="actions seed-actions"><button class="btn primary" data-action="savePartner" type="button">Enregistrer stockage</button><button class="btn light" data-action="selectPartner" data-id="${selected.id}" type="button">Effacer</button></div>` : `<p class="empty">Sélectionne une ligne de producteur.</p>`}</section>
        </section>
      </section>
    </main>`;
  }

  function factoryView() {
    const rows = partnerRows("factory");
    const selected = selectedPartner(rows);
    const form = state.partnerForm || JSON.parse(JSON.stringify((selected && selected.harvest) || emptyHarvest()));
    return `<main class="factory-app soja-odoo-partner">${partnerSidebar("factory")}
      <section class="factory-main soja-odoo-full">
        <section class="factory-hero"><div class="factory-hero-copy"><h1>Feuille de suivi de la production</h1><p>Suivez les volumes prévus, les lots alimentables et les producteurs partagés avec l'usine.</p><div class="meta"><span class="pill info">Usine</span><span class="pill info">Production</span><span class="pill success">Odoo</span></div></div><div class="factory-brand"><span>SoSoja</span><strong>COMPANY NAME</strong><small>${new Date().toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}</small></div></section>
        ${partnerTopbar("factory")}${alerts()}
        <section class="factory-kpis"><div class="factory-kpi"><span>Volume prévu:</span><strong>${fmtNumber(sumRows(rows, (p) => p.harvest && p.harvest.forecastT), " t")}</strong></div><div class="factory-kpi"><span>Volume alimentable</span><strong>${fmtNumber(sumRows(rows, feedableQty), " t")}</strong></div><div class="factory-kpi"><span>Nombre de producteurs inscrits</span><strong>${rows.length}</strong><small>Selon le rôle</small></div></section>
        <section class="factory-dashboard">
          <section class="factory-card"><div class="factory-card-head"><div><h2>Prévisionnel partagé usine</h2><p>Filtre + export. Tous les producteurs Odoo sont visibles selon le partage.</p></div><span class="pill success">Odoo</span></div><div class="tablewrap factory-tablewrap"><table><thead><tr><th>Producteur</th><th>Zone</th><th>Téléphone</th><th>Email</th><th>Surface</th><th>Campagne</th><th>Date semence</th><th>Récolte prévue</th><th>Récolte effective</th><th>Qté prévue</th><th>Qté effective</th><th>Volume alimentable</th><th>Stockage</th><th>Stocké le</th><th>Note stockage</th><th>Décorticage</th><th>Broyage</th><th>Date traitement</th><th>Note traitement</th><th>Rendement</th><th>Partage</th><th></th></tr></thead><tbody>${rows.map((producer) => `<tr class="clickable-row ${selected && selected.id === producer.id ? "selected-row" : ""}" data-action="details" data-id="${producer.id}"><td><strong>${h(producer.name)}</strong></td><td>${h(producer.zone || "-")}</td><td>${h(producer.phone || "-")}</td><td>${h(producer.email || "-")}</td><td>${fmtNumber(producerArea(producer), " ha")}</td><td>${h((producer.harvest && producer.harvest.campaign) || "-")}</td><td>${fmtDate(producer.harvest && producer.harvest.seedDate)}</td><td>${fmtDate(producer.harvest && producer.harvest.harvestForecastDate)}</td><td>${fmtDate(producer.harvest && producer.harvest.harvestActualDate)}</td><td>${fmtNumber(producer.harvest && producer.harvest.forecastT, " t")}</td><td>${fmtNumber(producer.harvest && producer.harvest.actualT, " t")}</td><td>${fmtNumber(feedableQty(producer), " t")}</td><td>${stockLabel(producer.harvest)}</td><td>${fmtDate(producer.harvest && producer.harvest.stock && producer.harvest.stock.date)}</td><td>${h((producer.harvest && producer.harvest.stock && producer.harvest.stock.note) || "-")}</td><td>${producer.harvest && producer.harvest.factoryProcess && producer.harvest.factoryProcess.dehull ? "Oui" : "Non"}</td><td>${producer.harvest && producer.harvest.factoryProcess && producer.harvest.factoryProcess.grind ? "Oui" : "Non"}</td><td>${fmtDate(producer.harvest && producer.harvest.factoryProcess && producer.harvest.factoryProcess.date)}</td><td>${h((producer.harvest && producer.harvest.factoryProcess && producer.harvest.factoryProcess.note) || "-")}</td><td>${fmtNumber(producer.harvest && producer.harvest.yieldTha)}</td><td><span class="badge">${shareLabel(producer.harvest && producer.harvest.shareStatus)}</span></td><td><button class="btn compact light" data-action="selectPartner" data-id="${producer.id}" type="button">Suivre</button></td></tr>`).join("") || `<tr><td class="empty" colspan="22">Aucune donnée partagée avec l'usine.</td></tr>`}</tbody></table></div></section>
          <section class="factory-card factory-side-card"><div class="factory-card-head"><div><h2>Traitement usine</h2><p>Sélectionne une ligne pour consulter le potentiel de transformation.</p></div><span class="pill info">${h((selected && selected.name) || "Sélectionne une ligne")}</span></div>${selected ? `<div class="factory-process"><div class="process-status"><span>${form.factoryProcess && (form.factoryProcess.dehull || form.factoryProcess.grind) ? "Traitement planifié" : "Non planifié"}</span><strong>${fmtNumber(feedableQty(selected), " t")}</strong><small>Volume alimentable</small></div><div class="readonly-grid compact"><div><span>Producteur</span><strong>${h(selected.name)}</strong></div><div><span>Zone</span><strong>${h(selected.zone || "-")}</strong></div><div><span>Campagne</span><strong>${h((selected.harvest && selected.harvest.campaign) || "-")}</strong></div><div><span>Stockage</span><strong>${stockLabel(selected.harvest)}</strong></div><div><span>Date stockage</span><strong>${fmtDate(selected.harvest && selected.harvest.stock && selected.harvest.stock.date)}</strong></div><div><span>Note</span><strong>${h((selected.harvest && selected.harvest.stock && selected.harvest.stock.note) || "-")}</strong></div></div>${partnerEditor("factory", form, (selected.exploitations || []).find((item) => item.id === Number(form.exploitationId)))}<div class="actions seed-actions"><button class="btn primary" data-action="savePartner" type="button">Enregistrer</button><button class="btn danger" data-action="selectPartner" data-id="${selected.id}" type="button">Effacer</button>${canView("details") ? `<button class="btn primary" data-action="details" data-id="${selected.id}" type="button">Voir détails</button>` : ""}${canView("harvest") ? `<button class="btn light" data-view="harvest" data-id="${selected.id}" type="button">Mettre à jour récolte</button>` : ""}</div></div>` : `<p class="empty">Aucune ligne sélectionnée.</p>`}</section>
        </section>
      </section>
    </main>`;
  }

  function bankView() {
    const rows = partnerRows("bank");
    const selected = selectedPartner(rows);
    const form = state.partnerForm || JSON.parse(JSON.stringify((selected && selected.harvest) || emptyHarvest()));
    return `<main class="bank-app soja-odoo-partner">${partnerSidebar("bank")}
      <section class="bank-main soja-odoo-full">
        <section class="bank-hero"><h1>Vue banque</h1><p>Analysez les prévisionnels partagés et suivez les étapes de financement avec des signaux utiles.</p><div class="meta"><span class="pill info">Banque</span><span class="pill info">Risque</span><span class="pill info">Décaissement</span><span class="pill success">Odoo</span></div></section>
        ${partnerTopbar("bank")}${alerts()}
        <section class="bank-kpis"><div class="bank-kpi"><span>Prix de production total</span><strong>${fmtCurrency(sumRows(rows, productionCost))}</strong><small>Volume total: ${fmtNumber(sumRows(rows, (p) => p.harvest && p.harvest.forecastT), " t")}</small></div><div class="bank-kpi"><span>Financement total</span><strong>${fmtCurrency(sumRows(rows, (p) => p.harvest && p.harvest.bankLoan && p.harvest.bankLoan.requestedAmount) || sumRows(rows, productionCost))}</strong><small>Estimation à 200 FCFA/kg</small></div><div class="bank-kpi"><span>Dossiers reçus</span><strong>${rows.length}</strong><small>${rows.filter((p) => Number(p.harvest && p.harvest.bankLoan && p.harvest.bankLoan.requestedAmount) > 0).length} dossiers prioritaires</small></div></section>
        <section class="bank-dashboard">
          <section class="bank-card"><div class="bank-card-head"><div><h2>Circuit d'approbation d'un prêt bancaire</h2><p>Filtre + export. Clique une ligne pour ouvrir la page détails.</p></div><span class="pill success">Partagé</span></div><div class="tablewrap bank-tablewrap"><table><thead><tr><th>Producteur</th><th>Zone</th><th>Téléphone</th><th>Email</th><th>Surface</th><th>Campagne</th><th>Date semence</th><th>Récolte prévue</th><th>Récolte effective</th><th>Qté prévue</th><th>Qté effective</th><th>Rendement</th><th>Coût production</th><th>Financement demandé</th><th>Financement approuvé</th><th>Risque</th><th>Statut</th><th>Crédit en cours</th><th>Partage</th><th></th></tr></thead><tbody>${rows.map((producer) => `<tr class="clickable-row ${selected && selected.id === producer.id ? "selected-row" : ""}" data-action="details" data-id="${producer.id}"><td><strong>${h(producer.name)}</strong></td><td>${h(producer.zone || "-")}</td><td>${h(producer.phone || "-")}</td><td>${h(producer.email || "-")}</td><td>${fmtNumber(producerArea(producer), " ha")}</td><td>${h((producer.harvest && producer.harvest.campaign) || "-")}</td><td>${fmtDate(producer.harvest && producer.harvest.seedDate)}</td><td>${fmtDate(producer.harvest && producer.harvest.harvestForecastDate)}</td><td>${fmtDate(producer.harvest && producer.harvest.harvestActualDate)}</td><td>${fmtNumber(producer.harvest && producer.harvest.forecastT, " t")}</td><td>${fmtNumber(producer.harvest && producer.harvest.actualT, " t")}</td><td>${fmtNumber(producer.harvest && producer.harvest.yieldTha, " t/ha")}</td><td>${fmtCurrency(productionCost(producer))}</td><td>${fmtCurrency(producer.harvest && producer.harvest.bankLoan && producer.harvest.bankLoan.requestedAmount)}</td><td>${fmtCurrency(producer.harvest && producer.harvest.bankLoan && producer.harvest.bankLoan.approvedAmount)}</td><td>${h((producer.harvest && producer.harvest.bankLoan && producer.harvest.bankLoan.riskLevel) || "-")}</td><td>${h((producer.harvest && producer.harvest.bankLoan && producer.harvest.bankLoan.status) || "-")}</td><td>${h(producer.creditOngoing || "-")}</td><td><span class="badge">${shareLabel(producer.harvest && producer.harvest.shareStatus)}</span></td><td><button class="btn compact light" data-action="selectPartner" data-id="${producer.id}" type="button">Dossier</button></td></tr>`).join("") || `<tr><td class="empty" colspan="20">Aucun producteur en base.</td></tr>`}</tbody></table></div></section>
          <section class="bank-card"><div class="bank-card-head"><div><h2>En cours sur l'exploitation</h2><p>Informations de crédit ou d'investissement liées à la ligne sélectionnée.</p></div><span class="pill info">${h((selected && selected.name) || "-")}</span></div>${selected ? `<div class="bank-file"><div class="bank-file-card"><span>Emprunteur exploitant</span><strong>${h((form.bankLoan && form.bankLoan.borrowerType === "producer" && form.bankLoan.borrowerName) || selected.name || "-")}</strong></div><div class="bank-file-card"><span>Emprunt acheteur</span><strong>${h((form.bankLoan && form.bankLoan.borrowerType !== "producer" && form.bankLoan.borrowerName) || "-")}</strong></div><div class="readonly-grid compact"><div><span>Montant demandé</span><strong>${fmtCurrency(form.bankLoan && form.bankLoan.requestedAmount)}</strong></div><div><span>Montant approuvé</span><strong>${fmtCurrency(form.bankLoan && form.bankLoan.approvedAmount)}</strong></div><div><span>Risque</span><strong>${h((form.bankLoan && form.bankLoan.riskLevel) || "-")}</strong></div><div><span>Statut</span><strong>${h((form.bankLoan && form.bankLoan.status) || "-")}</strong></div><div><span>Crédit en cours</span><strong>${h(selected.creditOngoing || "-")}</strong></div><div><span>Campagne</span><strong>${h((selected.harvest && selected.harvest.campaign) || "-")}</strong></div></div>${partnerEditor("bank", form)}<div class="actions seed-actions"><button class="btn primary" data-action="savePartner" type="button">Enregistrer dossier</button><button class="btn danger" data-action="selectPartner" data-id="${selected.id}" type="button">Effacer dossier</button>${canView("details") ? `<button class="btn light" data-action="details" data-id="${selected.id}" type="button">Voir détails</button>` : ""}${canView("harvest") ? `<button class="btn light" data-view="harvest" data-id="${selected.id}" type="button">Récolte</button>` : ""}</div></div>` : `<p class="empty">Aucune exploitation sélectionnée.</p>`}</section>
        </section>
      </section>
    </main>`;
  }

  function partnerEditor(kind, form, exploitation = null) {
    if (kind === "cooperative") {
      return `<div class="form-grid seed-form"><label>Type stockage<select class="control" data-partner="stock.type"><option value="">-</option><option value="partial" ${form.stock.type === "partial" ? "selected" : ""}>Partiel</option><option value="total" ${form.stock.type === "total" ? "selected" : ""}>Total</option></select></label><label>Quantité stockée (t)<input class="control" type="number" step="0.01" data-partner="stock.qtyT" value="${h(form.stock.qtyT ?? "")}"/></label><label>Date stockage<input class="control" type="date" data-partner="stock.date" value="${h(form.stock.date || "")}"/></label><label>Note stockage<input class="control" data-partner="stock.note" value="${h(form.stock.note || "")}"/></label><label>Partage<select class="control" data-partner="shareStatus">${["partners", "cooperative", "factory", "bank", "private"].map((status) => `<option value="${status}" ${form.shareStatus === status ? "selected" : ""}>${shareLabel(status)}</option>`).join("")}</select></label></div>`;
    }
    if (kind === "factory") {
      return `<div class="factory-form-grid"><label><input type="checkbox" data-partner="factoryProcess.dehull" ${form.factoryProcess.dehull ? "checked" : ""}/> Décortiquer ?</label><label><input type="checkbox" data-partner="factoryProcess.grind" ${form.factoryProcess.grind ? "checked" : ""}/> Broyer ?</label><label>Stockage source<select class="control" data-partner="factoryProcess.storageInfoId"><option value="">Aucun</option>${(exploitation && exploitation.storageInfos || []).map((storage) => `<option value="${storage.id}" ${Number(form.factoryProcess.storageInfoId) === storage.id ? "selected" : ""}>${h(`${storage.cooperativeName || "Coopérative"} - ${fmtDate(storage.date)} - ligne #${storage.id}`)}</option>`).join("")}</select></label><label>Date prévue<input class="control" type="date" data-partner="factoryProcess.date" value="${h(form.factoryProcess.date || "")}"/></label><label>Note<input class="control" data-partner="factoryProcess.note" value="${h(form.factoryProcess.note || "")}"/></label><label>Partage<select class="control" data-partner="shareStatus">${["partners", "factory", "cooperative", "bank", "private"].map((status) => `<option value="${status}" ${form.shareStatus === status ? "selected" : ""}>${shareLabel(status)}</option>`).join("")}</select></label></div>`;
    }
    return `<div class="bank-loan-form"><label>Type emprunteur<select class="control" data-partner="bankLoan.borrowerType"><option value="">-</option><option value="producer" ${form.bankLoan.borrowerType === "producer" ? "selected" : ""}>Exploitant</option><option value="buyer" ${form.bankLoan.borrowerType === "buyer" ? "selected" : ""}>Acheteur</option><option value="cooperative" ${form.bankLoan.borrowerType === "cooperative" ? "selected" : ""}>Coopérative</option></select></label><label>Nom emprunteur<input class="control" data-partner="bankLoan.borrowerName" value="${h(form.bankLoan.borrowerName || "")}"/></label><label>Montant demandé<input class="control" type="number" step="1" data-partner="bankLoan.requestedAmount" value="${h(form.bankLoan.requestedAmount ?? "")}"/></label><label>Montant approuvé<input class="control" type="number" step="1" data-partner="bankLoan.approvedAmount" value="${h(form.bankLoan.approvedAmount ?? "")}"/></label><label>Risque<select class="control" data-partner="bankLoan.riskLevel"><option value="">-</option>${["Faible", "Standard", "À surveiller", "Prioritaire"].map((risk) => `<option ${form.bankLoan.riskLevel === risk ? "selected" : ""}>${risk}</option>`).join("")}</select></label><label>Statut<select class="control" data-partner="bankLoan.status"><option value="">-</option>${["Dossier reçu", "Analyse risque", "Proposition financement", "Approuvé", "Refusé", "Décision en attente"].map((status) => `<option ${form.bankLoan.status === status ? "selected" : ""}>${status}</option>`).join("")}</select></label><label>Date décision<input class="control" type="date" data-partner="bankLoan.decisionDate" value="${h(form.bankLoan.decisionDate || "")}"/></label><label>Note<input class="control" data-partner="bankLoan.note" value="${h(form.bankLoan.note || "")}"/></label><label>Partage<select class="control" data-partner="shareStatus">${["bank", "partners", "cooperative", "factory", "private"].map((status) => `<option value="${status}" ${form.shareStatus === status ? "selected" : ""}>${shareLabel(status)}</option>`).join("")}</select></label></div>`;
  }

  function currentViewHtml() {
    if (!state.session) return `<main class="mc-main"><section class="panel-section"><h2>Chargement...</h2></section></main>`;
    if (!canView(state.view)) state.view = defaultView();
    const logoutButton = `<button class="soja-global-logout" data-action="logout" type="button">Déconnexion</button>`;
    if (state.view === "entry") return `${entryView()}${logoutButton}`;
    if (state.view === "details") return `${detailsView()}${logoutButton}`;
    if (state.view === "seed") return `${seedHarvestView("seed")}${logoutButton}`;
    if (state.view === "harvest") return `${seedHarvestView("harvest")}${logoutButton}`;
    if (state.view === "cooperative") return `${coopView()}${logoutButton}`;
    if (state.view === "factory") return `${factoryView()}${logoutButton}`;
    if (state.view === "bank") return `${bankView()}${logoutButton}`;
    return `${listView()}${logoutButton}`;
  }

  function render() {
    const app = document.getElementById("soja-app");
    app.innerHTML = currentViewHtml();
    if (state.view === "cooperative" || state.view === "factory" || state.view === "bank") {
      const producer = selectedProducer();
      const form = state.partnerForm || emptyHarvest();
      const headerSelector = state.view === "cooperative" ? ".coop-dashboard .coop-card:last-child .coop-card-head" : state.view === "factory" ? ".factory-side-card .factory-card-head" : ".bank-dashboard .bank-card:last-child .bank-card-head";
      const panelHeader = app.querySelector(headerSelector);
      if (producer && panelHeader) {
        if (state.view !== "cooperative") panelHeader.insertAdjacentHTML("afterend", partnerExploitationSelector(producer, form));
        panelHeader.insertAdjacentHTML("afterend", partnerOperationSummary(producer, form, state.view));
      }
    }
  }

  function partnerExploitationSelector(producer, form) {
    return `<label>Exploitation suivie<select class="control" data-partner-exploitation="1">${(producer.exploitations || []).map((item) => `<option value="${item.id}" ${Number(form.exploitationId) === item.id ? "selected" : ""}>${h(item.name)} - ${fmtNumber(item.areaHa, " ha")}</option>`).join("")}</select></label>`;
  }

  function partnerOperationSummary(producer, form, kind) {
    const exploitation = (producer.exploitations || []).find((item) => item.id === Number(form.exploitationId));
    if (!exploitation) return "";
    const rows = kind === "cooperative" ? exploitation.storageInfos || [] : kind === "factory" ? exploitation.treatmentInfos || [] : exploitation.bankInfos || [];
    const title = kind === "cooperative" ? "Stockages de cette exploitation" : kind === "factory" ? "Traitements de cette exploitation" : "Dossiers bancaires de cette exploitation";
    const headers = kind === "cooperative" ? ["Coopérative", "Type", "Quantité", "Date"] : kind === "factory" ? ["Usine", "Décorticage", "Broyage", "Date"] : ["Banque", "Demandé", "Approuvé", "Statut"];
    const cells = rows.map((item) => kind === "cooperative"
      ? `<tr><td>${h(item.cooperativeName || "-")}</td><td>${h(item.type || "-")}</td><td>${fmtNumber(item.quantityT, " t")}</td><td>${fmtDate(item.date)}</td></tr>`
      : kind === "factory"
        ? `<tr><td>${h(item.factoryName || "-")}</td><td>${item.dehull ? "Oui" : "Non"}</td><td>${item.grind ? "Oui" : "Non"}</td><td>${fmtDate(item.date)}</td></tr>`
        : `<tr><td>${h(item.bankName || "-")}</td><td>${fmtCurrency(item.requestedAmount)}</td><td>${fmtCurrency(item.approvedAmount)}</td><td>${h(item.status || "-")}</td></tr>`).join("");
    const actionCell = (item) => `<td><button class="btn compact light" data-action="selectOperation" data-kind="${kind}" data-id="${item.id}" type="button">Modifier</button><button class="btn compact danger" data-action="deleteOperation" data-kind="${kind}" data-id="${item.id}" type="button">Supprimer</button></td>`;
    const tableCells = rows.map((item) => {
      const row = kind === "cooperative"
        ? `<td>${h(item.cooperativeName || "-")}</td><td>${h(item.type || "-")}</td><td>${fmtNumber(item.quantityT, " t")}</td><td>${fmtDate(item.date)}</td>`
        : kind === "factory"
          ? `<td>${h(item.factoryName || "-")}</td><td>${item.dehull ? "Oui" : "Non"}</td><td>${item.grind ? "Oui" : "Non"}</td><td>${fmtDate(item.date)}</td>`
          : `<td>${h(item.bankName || "-")}</td><td>${fmtCurrency(item.requestedAmount)}</td><td>${fmtCurrency(item.approvedAmount)}</td><td>${h(item.status || "-")}</td>`;
      return `<tr>${row}${actionCell(item)}</tr>`;
    }).join("");
    const tableHeaders = `${headers.map((header) => `<th>${header}</th>`).join("")}<th>Actions</th>`;
    return `<section class="partner-operation-summary"><div class="section-head"><h3>${title}</h3><button class="btn light" data-action="newOperation" data-kind="${kind}" type="button">Nouvelle ligne</button></div><div class="tablewrap compact-table"><table><thead><tr>${tableHeaders}</tr></thead><tbody>${tableCells || `<tr><td class="empty" colspan="${headers.length + 1}">Aucune information enregistrée pour cette exploitation.</td></tr>`}</tbody></table></div></section>`;
  }

  async function readJson(response) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) return response.json();
    const text = await response.text();
    const isLoginPage = response.url.includes("/web/login") || text.includes("<title>Odoo</title") || text.includes("Redirecting");
    return {
      error: isLoginPage
        ? "Session expirée ou accès refusé. Reconnecte-toi à Odoo."
        : "Réponse Odoo inattendue. Vérifie les logs serveur.",
    };
  }

  function acceptRemoteState(sessionData, producersData) {
    state.session = sessionData;
    state.producers = Array.isArray(producersData) ? producersData : [];
    state.isOnline = navigator.onLine !== false;
    if (state.selectedId && !state.producers.some((producer) => Number(producer.id) === Number(state.selectedId))) {
      state.selectedId = state.producers[0] ? state.producers[0].id : null;
    }
    if (!state.selectedId && state.producers[0]) {
      state.selectedId = state.producers[0].id;
    }
    if (!canView(state.view)) state.view = defaultView();
    syncFormsFromSelected();
  }

  function localizeProducerAfterSave(saved, wasCreate = false, tempId = null) {
    if (wasCreate && tempId !== null) {
      removeProducerFromState(tempId);
    }
    upsertProducerInState(saved);
  }

  function localizeHarvestAfterSave(producerId, payloadHarvest) {
    updateProducerFromHarvest(producerId, (producer) => {
      producer.harvest = producer.harvest || emptyHarvest();
      producer.harvest = {
        ...producer.harvest,
        ...clone(payloadHarvest),
        services: {
          ...(producer.harvest.services || {}),
          ...(payloadHarvest.services || {}),
        },
        stock: {
          ...(producer.harvest.stock || {}),
          ...(payloadHarvest.stock || {}),
        },
        factoryProcess: {
          ...(producer.harvest.factoryProcess || {}),
          ...(payloadHarvest.factoryProcess || {}),
        },
        bankLoan: {
          ...(producer.harvest.bankLoan || {}),
          ...(payloadHarvest.bankLoan || {}),
        },
      };
    });
  }

  function localizePartnerAfterSave(producerId, kind, operationPayload, operationId) {
    updateProducerFromOperations(producerId, kind, operationPayload, operationId);
  }

  async function syncQueuedWrites() {
    if (!offlineQueue.length || !navigator.onLine) return;
    state.syncingQueue = true;
    state.error = "";
    render();
    const remaining = [];
    for (let index = 0; index < offlineQueue.length; index += 1) {
      const entry = offlineQueue[index];
      try {
        const response = await fetch(entry.url, {
          method: entry.method,
          headers: entry.headers || { "Content-Type": "application/json" },
          body: entry.body === undefined ? undefined : JSON.stringify(entry.body),
        });
        const data = await readJson(response);
        if (!response.ok) {
          throw new Error(data.error || entry.description || "Synchronisation impossible.");
        }
        if (entry.kind === "producer-save" && entry.tempId !== null && data && data.id) {
          replaceQueuedTempIds(entry.tempId, data.id);
          if (Number(state.selectedId) === Number(entry.tempId)) {
            state.selectedId = data.id;
          }
          localizeProducerAfterSave(data, true, entry.tempId);
        } else if (entry.kind === "producer-delete" && entry.producerId !== null) {
          removeProducerFromState(entry.producerId);
        } else if (entry.kind === "harvest-save" && entry.producerId !== null) {
          localizeHarvestAfterSave(entry.producerId, entry.payloadHarvest);
        } else if (entry.kind === "partner-save" && entry.producerId !== null) {
          localizePartnerAfterSave(entry.producerId, entry.operationKind, entry.operationPayload, entry.operationId);
        } else if (entry.kind === "operation-delete" && entry.producerId !== null) {
          removeOperationFromState(entry.producerId, entry.operationKind, entry.operationId, entry.operationPayload.exploitationId);
        } else if (entry.kind === "harvest-delete" && entry.producerId !== null) {
          updateProducerFromHarvest(entry.producerId, (producer) => {
            producer.harvest = emptyHarvest();
          });
        }
      } catch (error) {
        if (isOfflineError(error)) {
          remaining.push(entry, ...offlineQueue.slice(index + 1));
          break;
        }
        state.error = error.message || "Synchronisation impossible.";
        remaining.push(entry, ...offlineQueue.slice(index + 1));
        break;
      }
    }
    offlineQueue = remaining;
    state.pendingWrites = offlineQueue.length;
    state.syncingQueue = false;
    if (!offlineQueue.length) {
      state.lastSyncAt = nowIso();
    }
    await persistOfflineState();
    render();
  }

  async function load() {
    await restoreOfflineState();
    state.isOnline = navigator.onLine !== false;
    if (!state.isOnline) {
      if (!state.producers.length) {
        state.error = "Aucune donnee locale disponible. Ouvre l'app une fois en ligne avant d'utiliser la tablette hors connexion.";
      }
      if (!state.selectedId && state.producers[0]) state.selectedId = state.producers[0].id;
      if (!canView(state.view)) state.view = defaultView();
      syncFormsFromSelected();
      render();
      return;
    }

    try {
      await syncQueuedWrites();
      const sessionResponse = await fetch(SESSION_API, { headers: { Accept: "application/json" } });
      const sessionData = await readJson(sessionResponse);
      if (!sessionResponse.ok) throw new Error(sessionData.error || "Acces SoSoja non autorise.");
      const response = await fetch(API, { headers: { Accept: "application/json" } });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.error || "Chargement impossible.");
      acceptRemoteState(sessionData, data.results || []);
      state.lastSyncAt = nowIso();
      state.error = "";
      state.notice = "Donnees synchronisees depuis Odoo.";
      await persistOfflineState();
      render();
    } catch (error) {
      state.isOnline = false;
      if (!state.producers.length) {
        const restored = await restoreOfflineState();
        if (!restored) {
          state.error = error.message || "Chargement impossible.";
          render();
          return;
        }
      }
      if (!state.selectedId && state.producers[0]) state.selectedId = state.producers[0].id;
      if (!canView(state.view)) state.view = defaultView();
      syncFormsFromSelected();
      state.error = "";
      state.notice = "Connexion indisponible. Les donnees locales sont utilisees.";
      render();
    }
  }

  async function syncAndLogoutAfterReconnect() {
    if (reconnectLogoutInProgress) return;
    reconnectLogoutInProgress = true;
    updateConnectivity();

    try {
      await syncQueuedWrites();
    } finally {
      window.location.assign("/soja/logout");
    }
  }

  async function saveProducer() {
    state.error = "";
    state.form.exploitations = (state.form.exploitations || []).map((exploitation) => ({
      ...exploitation,
      points: (exploitation.points || []).filter((point) => point && point.lon !== null && point.lon !== undefined && point.lon !== "" && point.lat !== null && point.lat !== undefined && point.lat !== ""),
    }));
    const method = state.form.id ? "PUT" : "POST";
    const url = state.form.id ? `${API}/${state.form.id}` : API;
    const payload = clone(state.form);
    const tempId = payload.id || nextTempId();
    try {
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const saved = await readJson(response);
      if (!response.ok) {
        throw new Error(saved.error || "Enregistrement impossible.");
      }
      localizeProducerAfterSave(saved, !state.form.id, tempId);
      state.notice = "Producteur enregistre dans Odoo.";
      state.selectedId = saved.id;
      state.view = "details";
      state.lastSyncAt = nowIso();
      await persistOfflineState();
      render();
    } catch (error) {
      if (!isOfflineError(error)) {
        state.error = error.message || "Enregistrement impossible.";
        render();
        return;
      }
      const offlineProducer = clone(payload);
      offlineProducer.id = state.form.id || tempId;
      if (!offlineProducer.createdAt) offlineProducer.createdAt = nowIso();
      upsertProducerInState(offlineProducer);
      state.selectedId = offlineProducer.id;
      state.view = "details";
      state.notice = "Producteur enregistre hors ligne. Synchronisation en attente.";
      await queueWrite({
        kind: "producer-save",
        method,
        url,
        body: payload,
        tempId: state.form.id ? null : tempId,
        producerId: state.form.id || null,
        description: "Enregistrement producteur",
      });
      await persistOfflineState();
      render();
    }
  }

  async function deleteProducer(id) {
    if (!confirm("Supprimer ce producteur ?")) return;
    const url = `${API}/${id}`;
    try {
      const response = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(data.error || "Suppression impossible.");
      }
      removeProducerFromState(id);
      state.notice = "Producteur supprime dans Odoo.";
      state.view = "list";
      state.selectedId = state.producers[0] ? state.producers[0].id : null;
      state.lastSyncAt = nowIso();
      await persistOfflineState();
      render();
    } catch (error) {
      if (!isOfflineError(error)) {
        state.error = error.message || "Suppression impossible.";
        render();
        return;
      }
      removeProducerFromState(id);
      state.notice = "Suppression enregistree hors ligne. Synchronisation en attente.";
      state.view = "list";
      await queueWrite({
        kind: "producer-delete",
        method: "DELETE",
        url,
        body: null,
        producerId: Number(id),
        description: "Suppression producteur",
      });
      await persistOfflineState();
      render();
    }
  }

  async function saveHarvest(kind) {
    const producer = selectedProducer();
    if (!producer) return;
    const form = kind === "seed" ? state.seedForm : state.harvestForm;
    const exploitation = ((producer.exploitations || []).find((item) => item.id === Number(form.exploitationId)) || primaryExploitation(producer) || {});
    const selectedHarvest = harvestForExploitation(producer, exploitation);
    const area = Number(exploitation.areaHa || producerArea(producer) || 0);
    const yieldValue = Number((kind === "seed" ? form.yieldTha : form.actualYieldTha) || 0);
    if (kind === "seed") form.forecastT = area && yieldValue ? area * yieldValue : form.forecastT;
    if (kind === "harvest") form.actualT = area && yieldValue ? area * yieldValue : form.actualT;
    const payloadHarvest = kind === "seed"
      ? { ...selectedHarvest, ...form, exploitationId: exploitation.id }
      : {
        id: selectedHarvest.id || null,
        exploitationId: exploitation.id,
        harvestActualDate: form.harvestActualDate,
        actualT: form.actualT,
        actualYieldTha: form.actualYieldTha,
      };
    const payload = { harvest: payloadHarvest };
    const url = `${API}/${producer.id}`;
    try {
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const saved = await readJson(response);
      if (!response.ok) {
        throw new Error(saved.error || "Enregistrement impossible.");
      }
      localizeProducerAfterSave(saved, false, null);
      state.notice = kind === "seed" ? "Prevision enregistree dans Odoo." : "Recolte enregistree dans Odoo.";
      state.lastSyncAt = nowIso();
      await persistOfflineState();
      render();
    } catch (error) {
      if (!isOfflineError(error)) {
        state.error = error.message || "Enregistrement impossible.";
        render();
        return;
      }
      localizeHarvestAfterSave(producer.id, payloadHarvest);
      state.notice = kind === "seed" ? "Prevision enregistree hors ligne. Synchronisation en attente." : "Recolte enregistree hors ligne. Synchronisation en attente.";
      await queueWrite({
        kind: "harvest-save",
        method: "PUT",
        url,
        body: payload,
        producerId: producer.id,
        payloadHarvest,
        description: "Enregistrement recolte",
      });
      await persistOfflineState();
      render();
    }
  }

  async function savePartner() {
    const producer = selectedProducer();
    if (!producer) return;
    if (["cooperative", "factory", "bank"].includes(state.view)) {
      const operation = state.view === "cooperative" ? "storage" : state.view === "factory" ? "treatment" : "bank";
      const operationKey = operation === "storage" ? "storageId" : operation === "treatment" ? "treatmentId" : "bankId";
      const operationId = state.partnerForm[operationKey] || null;
      const values = operation === "storage" ? state.partnerForm.stock : operation === "treatment" ? state.partnerForm.factoryProcess : state.partnerForm.bankLoan;
      const operationPayload = {
        operation,
        mode: operationId ? "update" : "create",
        [operationKey]: operationId,
        harvestId: state.partnerForm.id || null,
        exploitationId: state.partnerForm.exploitationId,
        [operation]: values,
      };
      const url = `${API}/${producer.id}/operations`;
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(operationPayload),
        });
        const saved = await readJson(response);
        if (!response.ok) {
          throw new Error(saved.error || "Enregistrement impossible.");
        }
        localizePartnerAfterSave(producer.id, state.view, operationPayload, operationId || null);
        state.notice = "Information enregistree dans Odoo.";
        state.lastSyncAt = nowIso();
        await persistOfflineState();
        render();
      } catch (error) {
        if (!isOfflineError(error)) {
          state.error = error.message || "Enregistrement impossible.";
          render();
          return;
        }
        localizePartnerAfterSave(producer.id, state.view, operationPayload, operationId || null);
        state.notice = "Information enregistree hors ligne. Synchronisation en attente.";
        await queueWrite({
          kind: "partner-save",
          method: "POST",
          url,
          body: operationPayload,
          producerId: producer.id,
          operationKind: state.view,
          operationPayload,
          operationId: operationId || null,
          description: "Enregistrement operation partenaire",
        });
        await persistOfflineState();
        render();
      }
      return;
    }
    const payload = { ...producer, harvest: { ...(producer.harvest || emptyHarvest()), ...state.partnerForm } };
    const url = `${API}/${producer.id}`;
    try {
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const saved = await readJson(response);
      if (!response.ok) {
        throw new Error(saved.error || "Enregistrement partenaire impossible.");
      }
      localizeProducerAfterSave(saved, false, null);
      state.notice = "Donnees partenaire enregistrees dans Odoo.";
      state.lastSyncAt = nowIso();
      await persistOfflineState();
      render();
    } catch (error) {
      if (!isOfflineError(error)) {
        state.error = error.message || "Enregistrement partenaire impossible.";
        render();
        return;
      }
      updateProducerFromHarvest(producer.id, (item) => {
        item.harvest = {
          ...(item.harvest || emptyHarvest()),
          ...clone(state.partnerForm),
        };
      });
      state.notice = "Donnees partenaire enregistrees hors ligne. Synchronisation en attente.";
      await queueWrite({
        kind: "partner-save",
        method: "PUT",
        url,
        body: payload,
        producerId: producer.id,
        operationKind: "harvest",
        operationPayload: {
          exploitationId: state.partnerForm.exploitationId,
          shareStatus: state.partnerForm.shareStatus,
          stock: state.partnerForm.stock,
          factoryProcess: state.partnerForm.factoryProcess,
          bankLoan: state.partnerForm.bankLoan,
        },
        operationId: null,
        description: "Enregistrement partenaire",
      });
      await persistOfflineState();
      render();
    }
  }

  async function deleteOperation(kind, operationId) {
    const producer = selectedProducer();
    const exploitationId = state.partnerForm && state.partnerForm.exploitationId;
    if (!producer || !operationId || !exploitationId || !confirm("Supprimer cette ligne ?")) return;
    const operation = kind === "cooperative" ? "storage" : kind === "factory" ? "treatment" : "bank";
    const query = new URLSearchParams({ operation, operation_id: operationId, exploitation_id: exploitationId });
    const url = `${API}/${producer.id}/operations?${query.toString()}`;
    try {
      const response = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(data.error || "Suppression impossible.");
      }
      state.notice = "Ligne supprimee dans Odoo.";
      removeOperationFromState(producer.id, kind, Number(operationId), exploitationId);
      state.lastSyncAt = nowIso();
      await persistOfflineState();
      render();
    } catch (error) {
      if (!isOfflineError(error)) {
        state.error = error.message || "Suppression impossible.";
        render();
        return;
      }
      state.notice = "Ligne supprimee hors ligne. Synchronisation en attente.";
      await queueWrite({
        kind: "operation-delete",
        method: "DELETE",
        url,
        body: null,
        producerId: producer.id,
        operationKind: kind,
        operationPayload: { exploitationId },
        operationId: Number(operationId),
        description: "Suppression operation partenaire",
      });
      await persistOfflineState();
      render();
    }
  }

  async function deleteHarvest(kind) {
    const producer = selectedProducer();
    if (!producer) return;
    const form = kind === "seed" ? state.seedForm : state.harvestForm;
    const params = new URLSearchParams();
    if (form.id) params.set("harvest_id", form.id);
    if (form.exploitationId) params.set("exploitation_id", form.exploitationId);
    const suffix = kind === "harvest" ? "/actual" : "";
    const query = params.toString() ? `?${params.toString()}` : "";
    const url = `${API}/${producer.id}/harvest${suffix}${query}`;
    try {
      const response = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } });
      const data = await readJson(response);
      if (!response.ok) {
        throw new Error(data.error || "Suppression impossible.");
      }
      updateProducerFromHarvest(producer.id, (item) => {
        if (kind === "harvest") {
          item.harvest.harvestActualDate = null;
          item.harvest.actualT = null;
          item.harvest.actualYieldTha = null;
        } else {
          item.harvest = emptyHarvest();
        }
      });
      state.notice = "Donnees supprimees dans Odoo.";
      state.lastSyncAt = nowIso();
      await persistOfflineState();
      render();
    } catch (error) {
      if (!isOfflineError(error)) {
        state.error = error.message || "Suppression impossible.";
        render();
        return;
      }
      updateProducerFromHarvest(producer.id, (item) => {
        if (kind === "harvest") {
          item.harvest.harvestActualDate = null;
          item.harvest.actualT = null;
          item.harvest.actualYieldTha = null;
        } else {
          item.harvest = emptyHarvest();
        }
      });
      state.notice = "Suppression enregistree hors ligne. Synchronisation en attente.";
      await queueWrite({
        kind: kind === "harvest" ? "harvest-delete" : "harvest-delete",
        method: "DELETE",
        url,
        body: null,
        producerId: producer.id,
        description: "Suppression donnee recolte",
      });
      await persistOfflineState();
      render();
    }
  }

  function updateForm(target) {
    if (target.dataset.form) {
      const key = target.dataset.form;
      state.form[key] = target.type === "number" || key === "currentExploitationIndex" ? (target.value !== "" ? Number(target.value) : null) : target.value;
    }
    if (target.dataset.exploitationField) {
      const exploitation = formExploitation();
      const key = target.dataset.exploitationField;
      exploitation[key] = target.type === "number" ? (target.value !== "" ? Number(target.value) : null) : target.value;
      if (key === "areaHa") state.form.areaHa = exploitation.areaHa;
    }
    if (target.dataset.point) {
      const index = Number(target.dataset.point);
      const exploitation = formExploitation();
      exploitation.points[index] = exploitation.points[index] || { lon: null, lat: null };
      exploitation.points[index][target.dataset.axis] = target.value !== "" ? Number(target.value) : null;
      recalculatePlot();
    }
    if (target.dataset.harvest) {
      const form = state.view === "seed" ? state.seedForm : state.harvestForm;
      form[target.dataset.harvest] = target.type === "number" ? (target.value ? Number(target.value) : null) : target.value;
      if (target.dataset.harvest === "exploitationId") {
        const producer = selectedProducer();
        const exploitation = (producer && producer.exploitations || []).find((item) => item.id === Number(target.value));
        const selectedHarvest = harvestForExploitation(producer, exploitation);
        const nextForm = JSON.parse(JSON.stringify(selectedHarvest));
        nextForm.exploitationId = exploitation ? exploitation.id : null;
        if (state.view === "seed") state.seedForm = nextForm;
        if (state.view === "harvest") state.harvestForm = nextForm;
      }
    }
    if (target.dataset.harvestService) {
      const form = state.view === "seed" ? state.seedForm : state.harvestForm;
      form.services[target.dataset.harvestService] = target.checked;
    }
    if (target.dataset.partner) {
      const path = target.dataset.partner.split(".");
      let cursor = state.partnerForm;
      while (path.length > 1) cursor = cursor[path.shift()];
      const key = path[0];
      cursor[key] = target.type === "checkbox" ? target.checked : target.type === "number" ? (target.value ? Number(target.value) : null) : target.value;
    }
    if (target.dataset.partnerExploitation) {
      const producer = selectedProducer();
      const exploitation = (producer && producer.exploitations || []).find((item) => item.id === Number(target.value));
      state.partnerForm = JSON.parse(JSON.stringify(harvestForExploitation(producer, exploitation)));
      state.partnerForm.exploitationId = exploitation ? exploitation.id : null;
      render();
      return;
    }
    if (target.dataset.field === "query") state.query = target.value;
    if (target.dataset.field === "campaign") state.campaign = target.value;
    if (target.dataset.detailExploitation) {
      state.detailExploitationId = Number(target.value);
      state.detailCooperativeId = null;
      state.detailFactoryId = null;
      state.detailBankId = null;
      render();
      return;
    }
    if (target.dataset.detailOperation) {
      const stateKey = target.dataset.detailOperation === "cooperative" ? "detailCooperativeId" : target.dataset.detailOperation === "factory" ? "detailFactoryId" : "detailBankId";
      state[stateKey] = Number(target.value) || null;
      render();
      return;
    }
    if (target.dataset.field === "selectedId") {
      if (Number(state.selectedId) !== Number(target.value)) {
        state.selectedId = Number(target.value);
        state.detailExploitationId = null;
        state.detailCooperativeId = null;
        state.detailFactoryId = null;
        state.detailBankId = null;
      }
      const producer = selectedProducer();
      state.seedForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      state.harvestForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      state.partnerForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      render();
    }
  }

  document.addEventListener("input", (event) => updateForm(event.target));
  document.addEventListener("change", (event) => {
    updateForm(event.target);
    if (event.target.dataset.field === "campaign" || event.target.dataset.field === "query" || event.target.dataset.form === "currentExploitationIndex" || event.target.dataset.harvest === "exploitationId") render();
  });
  document.addEventListener("submit", (event) => {
    if (event.target.dataset.action === "save") {
      event.preventDefault();
      saveProducer();
    }
  });
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-view],[data-action]");
    if (!target) return;
    if (target.dataset.view) {
      event.preventDefault();
      if (!canView(target.dataset.view)) {
        state.error = "Accès non autorisé pour ce rôle.";
        render();
        return;
      }
      state.view = target.dataset.view;
      if (target.dataset.id && Number(state.selectedId) !== Number(target.dataset.id)) {
        state.selectedId = Number(target.dataset.id);
        state.detailExploitationId = null;
      }
      const producer = selectedProducer();
      if (state.view === "entry") state.form = emptyProducer();
      if (state.view === "seed") state.seedForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      if (state.view === "harvest") state.harvestForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      if (["cooperative", "factory", "bank"].includes(state.view)) state.partnerForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      render();
      return;
    }
    const action = target.dataset.action;
    if (action === "logout") {
      window.location.href = "/soja/logout";
      return;
    }
    if (action === "reload") {
      if (!state.isOnline || navigator.onLine === false) return;
      load();
      return;
    }
    if (action === "useSaveExample") {
      formExploitation().points = JSON.parse(JSON.stringify(SAVE_POINTS));
      recalculatePlot();
      render();
    }
    if (action === "addPoint") {
      const exploitation = formExploitation();
      exploitation.points = normalizedPointRows(exploitation.points);
      exploitation.points.push({ lon: null, lat: null });
      render();
    }
    if (action === "removePoint") {
      const exploitation = formExploitation();
      const index = Number(target.dataset.pointIndex);
      exploitation.points = normalizedPointRows(exploitation.points);
      if (Number.isInteger(index) && exploitation.points.length > 1) {
        exploitation.points.splice(index, 1);
        recalculatePlot();
      }
      render();
    }
    if (action === "locatePoint") {
      locatePoint(Number(target.dataset.pointIndex));
    }
    if (action === "addExploitation") {
      state.form.exploitations = Array.isArray(state.form.exploitations) ? state.form.exploitations : [];
      state.form.exploitations.push({ ...emptyExploitation(), name: `Exploitation SoSoja ${state.form.exploitations.length + 1}` });
      state.form.currentExploitationIndex = state.form.exploitations.length - 1;
      render();
    }
    if (action === "removeExploitation") {
      state.form.exploitations = Array.isArray(state.form.exploitations) ? state.form.exploitations : [emptyExploitation()];
      if (state.form.exploitations.length > 1) state.form.exploitations.splice(state.form.currentExploitationIndex || 0, 1);
      state.form.currentExploitationIndex = 0;
      render();
    }
    if (action === "selectPartner") {
      if (Number(state.selectedId) !== Number(target.dataset.id)) {
        state.selectedId = Number(target.dataset.id);
        state.detailExploitationId = null;
      }
      const producer = selectedProducer();
      state.partnerForm = JSON.parse(JSON.stringify((producer && producer.harvest) || emptyHarvest()));
      render();
    }
    if (action === "selectExploitation") {
      state.detailExploitationId = Number(target.dataset.id);
      render();
    }
    if (action === "details") {
      if (!canView("details")) {
        state.error = "Accès non autorisé pour ce rôle.";
        render();
        return;
      }
      if (Number(state.selectedId) !== Number(target.dataset.id)) {
        state.selectedId = Number(target.dataset.id);
        state.detailExploitationId = null;
      }
      state.view = "details";
      render();
    }
    if (action === "edit") {
      if (!canView("entry")) {
        state.error = "Accès non autorisé pour ce rôle.";
        render();
        return;
      }
      const producer = state.producers.find((item) => item.id === Number(target.dataset.id));
      if (producer) {
        state.form = JSON.parse(JSON.stringify(producer));
        state.view = "entry";
        render();
      }
    }
    if (action === "delete") deleteProducer(target.dataset.id);
    if (action === "saveSeed") saveHarvest("seed");
    if (action === "saveHarvest") saveHarvest("harvest");
    if (action === "savePartner") savePartner();
    if (action === "selectOperation") {
      const producer = selectedProducer();
      const kind = target.dataset.kind;
      const collection = kind === "cooperative" ? "storageInfos" : kind === "factory" ? "treatmentInfos" : "bankInfos";
      const exploitation = producer && (producer.exploitations || []).find((item) => (item[collection] || []).some((operation) => operation.id === Number(target.dataset.id)));
      const operation = exploitation && (exploitation[collection] || []).find((item) => item.id === Number(target.dataset.id));
      if (producer && exploitation && operation) {
        state.partnerForm = JSON.parse(JSON.stringify(harvestForExploitation(producer, exploitation)));
        state.partnerForm.exploitationId = exploitation.id;
        if (kind === "cooperative") {
          state.partnerForm.storageId = operation.id;
          state.partnerForm.stock = { type: operation.type || "", qtyT: operation.quantityT, date: operation.date || null, note: operation.note || "" };
        } else if (kind === "factory") {
          state.partnerForm.treatmentId = operation.id;
          state.partnerForm.factoryProcess = { dehull: operation.dehull, grind: operation.grind, storageInfoId: operation.storageInfoId || null, date: operation.date || null, note: operation.note || "" };
        } else {
          state.partnerForm.bankId = operation.id;
          state.partnerForm.bankLoan = { borrowerType: operation.borrowerType || "", borrowerName: operation.borrowerName || "", requestedAmount: operation.requestedAmount, approvedAmount: operation.approvedAmount, riskLevel: operation.riskLevel || "", status: operation.status || "", decisionDate: operation.date || null, note: operation.note || "" };
        }
        render();
      }
    }
    if (action === "newOperation") {
      const producer = selectedProducer();
      const kind = target.dataset.kind;
      const exploitation = producer && (producer.exploitations || []).find((item) => item.id === Number(state.partnerForm && state.partnerForm.exploitationId));
      state.partnerForm = JSON.parse(JSON.stringify(harvestForExploitation(producer, exploitation)));
      state.partnerForm.exploitationId = exploitation ? exploitation.id : null;
      if (kind === "cooperative") {
        state.partnerForm.storageId = null;
        state.partnerForm.stock = { type: "", qtyT: null, date: null, note: "" };
      } else if (kind === "factory") {
        state.partnerForm.treatmentId = null;
        state.partnerForm.factoryProcess = { dehull: false, grind: false, storageInfoId: null, date: null, note: "" };
      } else {
        state.partnerForm.bankId = null;
        state.partnerForm.bankLoan = { borrowerType: "", borrowerName: "", requestedAmount: null, approvedAmount: null, riskLevel: "", status: "", decisionDate: null, note: "" };
      }
      render();
    }
    if (action === "deleteOperation") deleteOperation(target.dataset.kind, target.dataset.id);
    if (action === "deleteSeed") deleteHarvest("seed");
    if (action === "deleteHarvest") deleteHarvest("harvest");
    if (action === "export") {
      const blob = new Blob([JSON.stringify(filteredProducers(), null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "producteurs_soja_odoo.json";
      anchor.click();
      URL.revokeObjectURL(url);
    }
  });

  async function registerOfflineSupport() {
    if (!("serviceWorker" in navigator)) return;
    try {
      await navigator.serviceWorker.register(`/soja/sw.js?v=${encodeURIComponent(ASSET_VERSION)}`, { scope: "/soja/" });
    } catch {
      return;
    }
  }

  async function bootstrap() {
    window.addEventListener("online", () => {
      syncAndLogoutAfterReconnect().catch(() => {
        window.location.assign("/soja/logout");
      });
    });
    window.addEventListener("offline", updateConnectivity);

    // Empêcher l'actualisation ou la navigation hors de la page en mode hors ligne via beforeunload
    window.addEventListener("beforeunload", (event) => {
      if (!state.isOnline || navigator.onLine === false) {
        const message = "Attention : vous êtes hors ligne. Si vous actualisez ou quittez, vous perdrez toutes les données non synchronisées et l'accès à l'application.";
        event.preventDefault();
        event.returnValue = message;
        return message;
      }
    });

    // Bloquer les raccourcis clavier d'actualisation (F5, Ctrl+R, Cmd+R, Ctrl+Shift+R, Cmd+Shift+R) en mode hors ligne
    window.addEventListener("keydown", (event) => {
      if (!state.isOnline || navigator.onLine === false) {
        const isR = event.key === "r" || event.key === "R" || event.keyCode === 82;
        const isF5 = event.key === "F5" || event.keyCode === 116;
        if (isF5 || ((event.ctrlKey || event.metaKey) && isR)) {
          event.preventDefault();
        }
      }
    });

    await registerOfflineSupport();
    await load();
  }

  bootstrap().catch((error) => {
    state.error = error.message || "Chargement impossible.";
    render();
  });
}());
