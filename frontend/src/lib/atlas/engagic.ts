export type AtlasTone = 'source' | 'sync' | 'process' | 'store' | 'serve';

export type AtlasNode = {
	id: string;
	parent?: string;
	label: string;
	kicker: string;
	description?: string;
	file?: string;
	tone: AtlasTone;
	depth: 0 | 1 | 2;
	reveal: number;
	detailReveal?: number;
	x: number;
	y: number;
	w: number;
	h: number;
	details?: string[];
};

export type AtlasEdge = {
	id: string;
	from: string;
	to: string;
	label?: string;
	tone: AtlasTone;
	reveal: number;
	maxReveal?: number;
	dashed?: boolean;
};

export const WORLD = { width: 1700, height: 960 } as const;

const ATLAS_NODE_SOURCE: AtlasNode[] = [
	{
		id: 'engagic',
		label: 'ENGAGIC',
		kicker: 'MUNICIPAL RECORD INFRASTRUCTURE',
		description: 'Discover · preserve · understand · publish',
		tone: 'sync',
		depth: 0,
		reveal: 0,
		x: 40,
		y: 40,
		w: 2320,
		h: 1320
	},
	{
		id: 'vendors',
		parent: 'engagic',
		label: 'VENDOR NETWORK',
		kicker: '01 · ACQUIRE',
		description: '22 civic platform adapters → one meeting contract.',
		tone: 'source',
		depth: 1,
		reveal: 1.3,
		x: 100,
		y: 210,
		w: 390,
		h: 770
	},
	{
		id: 'sync',
		parent: 'engagic',
		label: 'SYNC LOOP',
		kicker: '02 · DISCOVER',
		description: 'Vendor-aware discovery → durable civic records.',
		tone: 'sync',
		depth: 1,
		reveal: 1.3,
		x: 560,
		y: 130,
		w: 480,
		h: 500
	},
	{
		id: 'processing',
		parent: 'engagic',
		label: 'PROCESSING LOOP',
		kicker: '03 · UNDERSTAND',
		description: 'Claim jobs → acquire → filter → summarize → normalize.',
		tone: 'process',
		depth: 1,
		reveal: 1.3,
		x: 560,
		y: 700,
		w: 480,
		h: 590
	},
	{
		id: 'storage',
		parent: 'engagic',
		label: 'SOURCE OF TRUTH',
		kicker: '04 · REMEMBER',
		description: 'PostgreSQL owns state; R2 preserves source documents.',
		tone: 'store',
		depth: 1,
		reveal: 1.3,
		x: 1120,
		y: 190,
		w: 500,
		h: 1010
	},
	{
		id: 'delivery',
		parent: 'engagic',
		label: 'PUBLIC SURFACES',
		kicker: '05 · SERVE',
		description: 'Cache-first APIs power web, alerts, and participation.',
		tone: 'serve',
		depth: 1,
		reveal: 1.3,
		x: 1700,
		y: 270,
		w: 600,
		h: 850
	},

	// Vendor network
	{
		id: 'vendor-factory', parent: 'vendors', label: 'ADAPTER FACTORY', kicker: 'ROUTING',
		file: 'vendors/factory.py', tone: 'source', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 125, y: 285, w: 145, h: 150,
		details: ['VENDOR_ADAPTERS', 'get_async_adapter()', 'vendor → class', 'Legistar token path']
	},
	{
		id: 'vendor-adapters', parent: 'vendors', label: '22 ASYNC ADAPTERS', kicker: 'UNIFIED CONTRACT',
		file: 'vendors/adapters/', tone: 'source', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 290, y: 285, w: 170, h: 355,
		details: [
			'Granicus', 'Legistar', 'PrimeGov', 'IQM2', 'NovusAgenda', 'CivicClerk',
			'CivicPlus', 'CivicEngage', 'CivicWeb', 'eScribe', 'Municode', 'OnBase',
			'ProudCity', 'Vision Internet', 'WP Events', 'AgendaOnline', 'BoardBook',
			'Destiny', 'Berkeley', 'Chicago', 'Menlo Park', 'Ross'
		]
	},
	{
		id: 'vendor-parsers', parent: 'vendors', label: 'AGENDA PARSERS', kicker: 'HTML · PDF · TEXT',
		file: 'vendors/adapters/parsers/', tone: 'source', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 125, y: 475, w: 145, h: 220,
		details: ['router.py', 'agenda_chunker_v2.py', 'quality.py', 'pdf_profile.py', 'vendor-specific parsers']
	},
	{
		id: 'vendor-sessions', parent: 'vendors', label: 'NETWORK GUARDS', kicker: 'POLITE CRAWLING',
		file: 'vendors/', tone: 'source', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 125, y: 735, w: 145, h: 175,
		details: ['AsyncRateLimiter', 'SessionManager', 'retry budgets', 'signed URL handling']
	},
	{
		id: 'vendor-custom', parent: 'vendors', label: 'CUSTOM SOURCES', kicker: 'JURISDICTION-SPECIFIC',
		file: 'vendors/adapters/custom/', tone: 'source', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 290, y: 680, w: 170, h: 230,
		details: ['Berkeley adapter', 'Chicago adapter', 'Menlo Park adapter', 'Ross adapter', 'stable vendor ids']
	},

	// Sync loop
	{
		id: 'fetcher', parent: 'sync', label: 'FETCHER', kicker: 'SYNC COORDINATOR',
		file: 'pipeline/fetcher.py', tone: 'sync', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 590, y: 210, w: 190, h: 160,
		details: ['sync_all()', 'sync_cities()', 'sync_city()', '_sync_with_vendor()', 'CITY_SYNC_CONCURRENCY = 8']
	},
	{
		id: 'scheduler', parent: 'sync', label: 'ADAPTIVE SCHEDULE', kicker: 'ACTIVITY-AWARE',
		file: 'pipeline/fetcher.py', tone: 'sync', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 810, y: 210, w: 200, h: 160,
		details: ['8+ meetings → 12h', '4–7 meetings → 24h', '<4 meetings → 7d', 'never synced → now']
	},
	{
		id: 'meeting-sync', parent: 'sync', label: 'MEETING SYNC ORCHESTRATOR', kicker: 'TRANSACTION BOUNDARY',
		file: 'pipeline/orchestrators/meeting_sync.py', tone: 'sync', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 590, y: 410, w: 420, h: 170,
		details: ['store meeting + items', 'matter identity + appearances', 'committees + rosters', 'votes + sponsors', 'versioned outbox intent']
	},

	// Processing loop
	{
		id: 'queue-claims', parent: 'processing', label: 'QUEUE CLAIMS', kicker: 'OWNED WORK',
		file: 'database/repositories_async/queue.py', tone: 'process', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 590, y: 770, w: 190, h: 150,
		details: ['typed jobs', 'priority ordering', 'FOR UPDATE SKIP LOCKED', 'claim token', 'work version']
	},
	{
		id: 'job-runner', parent: 'processing', label: 'JOB RUNNER', kicker: 'LIFECYCLE',
		file: 'pipeline/job_runner.py', tone: 'process', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 820, y: 770, w: 190, h: 150,
		details: ['heartbeat', 'claim-loss guard', 'timeout policy', 'terminal outcomes', 'durable attempts']
	},
	{
		id: 'stream-lane', parent: 'processing', label: 'STREAMING LANE', kicker: 'URGENT WINDOW',
		file: 'pipeline/processor.py', tone: 'process', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 590, y: 960, w: 190, h: 120,
		details: ['next 24h', 'matter jobs', 'undated meetings', 'concurrency 6', 'single-item calls']
	},
	{
		id: 'batch-lane', parent: 'processing', label: 'BATCH LANE', kicker: 'BULK THROUGHPUT',
		file: 'pipeline/processor.py', tone: 'process', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 820, y: 960, w: 190, h: 120,
		details: ['non-urgent meetings', 'Gemini Batch API', '50% token cost', 'durable provider jobs', 'leased collector']
	},
	{
		id: 'documents', parent: 'processing', label: 'DOCUMENT ACQUISITION', kicker: 'CORPUS FIRST',
		file: 'pipeline/document_acquisition.py', tone: 'process', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 590, y: 1120, w: 190, h: 125,
		details: ['single-flight acquire', 'media-type dispatch', 'content SHA-256', 'PDF · Office · RTF · HTML', 'OCR fallback']
	},
	{
		id: 'analysis', parent: 'processing', label: 'ITEM ANALYSIS', kicker: 'STRUCTURED OUTPUT',
		file: 'analysis/', tone: 'process', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 820, y: 1120, w: 190, h: 125,
		details: ['AsyncAnalyzer', 'Summarizer', 'prompts v3', 'TopicNormalizer', 'incremental saves']
	},

	// Storage
	{
		id: 'db-facade', parent: 'storage', label: 'DATABASE FACADE', kicker: 'ASYNC POOL',
		file: 'database/db_postgres.py', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1150, y: 260, w: 200, h: 150,
		details: ['Database.create()', 'asyncpg pool', '17 repositories', 'JSONB codecs', 'platform metrics cache']
	},
	{
		id: 'core-tables', parent: 'storage', label: 'CIVIC RECORD', kicker: 'CORE TABLES',
		file: 'database/schema_postgres.sql', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1380, y: 260, w: 210, h: 240,
		details: ['jurisdictions', 'zipcodes', 'meetings', 'items', 'meeting_topics', 'item_topics', 'committees', 'committee_members']
	},
	{
		id: 'legislative-tables', parent: 'storage', label: 'LEGISLATIVE MEMORY', kicker: 'MATTERS · PEOPLE · VOTES',
		file: 'database/schema_postgres.sql', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1150, y: 455, w: 200, h: 235,
		details: ['city_matters', 'matter_appearances', 'matter_topics', 'council_members', 'sponsorships', 'votes', 'meeting_revisions', 'item_revisions']
	},
	{
		id: 'lifecycle-tables', parent: 'storage', label: 'PIPELINE MEMORY', kicker: 'QUEUE · OUTBOX · AUDIT',
		file: 'database/schema_postgres.sql', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1380, y: 540, w: 210, h: 235,
		details: ['queue', 'batch_jobs', 'pipeline_runs', 'job_attempts', 'pipeline_stage_events', 'pipeline_outbox', 'item_filter_audits', 'meeting_ingest_audits']
	},
	{
		id: 'corpus-index', parent: 'storage', label: 'CORPUS INDEX', kicker: 'POINTER + PROVENANCE',
		file: 'database/migrations/025_document_corpus.sql', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1150, y: 735, w: 200, h: 210,
		details: ['document_blob', 'document_source', 'document_ingest_failure', 'source identity', 'extract method + version', 'page + OCR counts']
	},
	{
		id: 'r2-corpus', parent: 'storage', label: 'R2 CORPUS', kicker: 'CONTENT-ADDRESSED OBJECTS',
		file: 'corpus/store.py', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1380, y: 820, w: 210, h: 175,
		details: ['originals/<sha256>', 'text/<sha256>.txt', 'deduplicated bytes', 're-extractable text', 'append-only evidence']
	},
	{
		id: 'userland-store', parent: 'storage', label: 'ENGAGEMENT STATE', kicker: 'USERLAND SCHEMA',
		file: 'database/schema_userland.sql', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1150, y: 995, w: 200, h: 150,
		details: ['users', 'alerts', 'alert_matches', 'watches', 'ratings', 'issues', 'magic links']
	},
	{
		id: 'repositories', parent: 'storage', label: 'DOMAIN REPOSITORIES', kicker: 'READ + WRITE CONTRACTS',
		file: 'database/repositories_async/', tone: 'store', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1380, y: 1040, w: 210, h: 105,
		details: ['items · meetings · matters', 'queue · batch · lifecycle', 'members · committees', 'search · engagement · userland']
	},

	// Public surfaces
	{
		id: 'fastapi', parent: 'delivery', label: 'FASTAPI SERVICE', kicker: 'CACHE-FIRST HTTP',
		file: 'server/main.py', tone: 'serve', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1730, y: 350, w: 220, h: 175,
		details: ['lifespan pool', 'request ids', 'rate limiting', 'Turnstile', 'Prometheus metrics', 'structured logs']
	},
	{
		id: 'api-routes', parent: 'delivery', label: '17 ROUTE MODULES', kicker: 'PUBLIC DATA CONTRACT',
		file: 'server/routes/', tone: 'serve', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1990, y: 350, w: 270, h: 255,
		details: ['search · meetings · topics', 'matters · votes · committees', 'auth · dashboard · engagement', 'feedback · deliberation', 'happening · events', 'admin · monitoring', 'flyer · donate']
	},
	{
		id: 'frontend', parent: 'delivery', label: 'SVELTEKIT WEB', kicker: 'CIVIC EXPERIENCE',
		file: 'frontend/src/', tone: 'serve', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1730, y: 570, w: 220, h: 205,
		details: ['SSR page loaders', 'city + meeting pages', 'matter timelines', 'council + committees', 'state exploration', 'Cloudflare deployment']
	},
	{
		id: 'alerts', parent: 'delivery', label: 'CIVIC ALERTS', kicker: 'MATCH + DELIVER',
		file: 'userland/', tone: 'serve', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1990, y: 650, w: 270, h: 155,
		details: ['magic-link auth', 'keyword matching', 'matter-based matching', 'weekly digest', 'Mailgun delivery', 'city watchlist']
	},
	{
		id: 'deliberation', parent: 'delivery', label: 'DELIBERATION', kicker: 'STRUCTURED PUBLIC INPUT',
		file: 'deliberation/', tone: 'serve', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1730, y: 825, w: 220, h: 165,
		details: ['PCA projection', 'dynamic K-means', 'consensus detection', 'comment votes', 'trust moderation']
	},
	{
		id: 'operations', parent: 'delivery', label: 'OPERATIONS', kicker: 'DEPLOY · OBSERVE · RECOVER',
		file: 'scripts/deploy.sh', tone: 'serve', depth: 2, reveal: 2.45,
		detailReveal: 5.7, x: 1990, y: 850, w: 270, h: 175,
		details: ['engagic-api.service', 'engagic-fetcher.service', 'processor runtime', 'schema migrations', 'health checks', 'Prometheus + journald']
	}
];

// The overview and component layers share one compact spatial index. Keeping the
// architecture copy separate from presentation geometry makes the map easy to
// tighten without touching the system description above.
const COMPACT_LAYOUT: Record<string, Pick<AtlasNode, 'x' | 'y' | 'w' | 'h'>> = {
	engagic: { x: 450, y: 80, w: 800, h: 800 },
	vendors: { x: 30, y: 330, w: 300, h: 300 },
	sync: { x: 360, y: 160, w: 280, h: 280 },
	processing: { x: 340, y: 520, w: 320, h: 320 },
	storage: { x: 760, y: 290, w: 380, h: 380 },
	delivery: { x: 1280, y: 310, w: 340, h: 340 },

	'vendor-factory': { x: 83, y: 378, w: 84, h: 84 },
	'vendor-adapters': { x: 193, y: 378, w: 84, h: 84 },
	'vendor-parsers': { x: 83, y: 483, w: 84, h: 84 },
	'vendor-sessions': { x: 193, y: 483, w: 84, h: 84 },
	'vendor-custom': { x: 138, y: 548, w: 84, h: 84 },

	fetcher: { x: 413, y: 223, w: 84, h: 84 },
	scheduler: { x: 503, y: 223, w: 84, h: 84 },
	'meeting-sync': { x: 458, y: 313, w: 84, h: 84 },

	'queue-claims': { x: 403, y: 558, w: 84, h: 84 },
	'job-runner': { x: 513, y: 558, w: 84, h: 84 },
	'stream-lane': { x: 403, y: 638, w: 84, h: 84 },
	'batch-lane': { x: 513, y: 638, w: 84, h: 84 },
	documents: { x: 403, y: 718, w: 84, h: 84 },
	analysis: { x: 513, y: 718, w: 84, h: 84 },

	'db-facade': { x: 834, y: 364, w: 72, h: 72 },
	'core-tables': { x: 914, y: 364, w: 72, h: 72 },
	'legislative-tables': { x: 994, y: 364, w: 72, h: 72 },
	'lifecycle-tables': { x: 834, y: 444, w: 72, h: 72 },
	'corpus-index': { x: 914, y: 444, w: 72, h: 72 },
	'r2-corpus': { x: 994, y: 444, w: 72, h: 72 },
	'userland-store': { x: 874, y: 524, w: 72, h: 72 },
	repositories: { x: 954, y: 524, w: 72, h: 72 },

	fastapi: { x: 1353, y: 358, w: 84, h: 84 },
	'api-routes': { x: 1463, y: 358, w: 84, h: 84 },
	frontend: { x: 1353, y: 438, w: 84, h: 84 },
	alerts: { x: 1463, y: 438, w: 84, h: 84 },
	deliberation: { x: 1353, y: 518, w: 84, h: 84 },
	operations: { x: 1463, y: 518, w: 84, h: 84 }
};

export const ATLAS_NODES: AtlasNode[] = ATLAS_NODE_SOURCE.map((node) => {
	const layout = COMPACT_LAYOUT[node.id];
	const geometry = node.depth === 2 && layout.w > 72
		? { x: layout.x + (layout.w - 72) / 2, y: layout.y + (layout.h - 72) / 2, w: 72, h: 72 }
		: layout;
	return { ...node, ...geometry };
});

export const ATLAS_EDGES: AtlasEdge[] = [
	{ id: 'trunk-vendor-sync', from: 'vendors', to: 'sync', label: 'meeting streams', tone: 'source', reveal: 1.3, maxReveal: 4.8 },
	{ id: 'trunk-sync-processing', from: 'sync', to: 'processing', label: 'versioned jobs', tone: 'sync', reveal: 1.3, maxReveal: 4.8 },
	{ id: 'trunk-sync-store', from: 'sync', to: 'storage', label: 'meetings · items · matters', tone: 'sync', reveal: 1.3, maxReveal: 4.8 },
	{ id: 'trunk-process-store', from: 'processing', to: 'storage', label: 'summaries · topics · corpus', tone: 'process', reveal: 1.3, maxReveal: 4.8 },
	{ id: 'trunk-store-serve', from: 'storage', to: 'delivery', label: 'cache-only reads', tone: 'store', reveal: 1.3, maxReveal: 4.8 },
	{ id: 'trunk-serve-store', from: 'delivery', to: 'storage', label: 'engagement writes', tone: 'serve', reveal: 1.3, maxReveal: 4.8, dashed: true },

	{ id: 'factory-adapters', from: 'vendor-factory', to: 'vendor-adapters', tone: 'source', reveal: 2.45 },
	{ id: 'adapters-fetcher', from: 'vendor-adapters', to: 'fetcher', label: 'fetch_meetings()', tone: 'source', reveal: 2.45 },
	{ id: 'parsers-meeting', from: 'vendor-parsers', to: 'meeting-sync', label: 'structured items', tone: 'source', reveal: 2.45 },
	{ id: 'sessions-fetcher', from: 'vendor-sessions', to: 'fetcher', tone: 'source', reveal: 2.45, dashed: true },
	{ id: 'custom-factory', from: 'vendor-custom', to: 'vendor-factory', tone: 'source', reveal: 2.45 },
	{ id: 'schedule-fetcher', from: 'scheduler', to: 'fetcher', label: 'due jurisdictions', tone: 'sync', reveal: 2.45 },
	{ id: 'fetcher-meeting', from: 'fetcher', to: 'meeting-sync', label: 'sync result', tone: 'sync', reveal: 2.45 },
	{ id: 'meeting-core', from: 'meeting-sync', to: 'core-tables', label: 'UPSERT', tone: 'sync', reveal: 2.45 },
	{ id: 'meeting-legislative', from: 'meeting-sync', to: 'legislative-tables', label: 'identity + votes', tone: 'sync', reveal: 2.45 },
	{ id: 'meeting-lifecycle', from: 'meeting-sync', to: 'lifecycle-tables', label: 'outbox intent', tone: 'sync', reveal: 2.45 },
	{ id: 'lifecycle-queue', from: 'lifecycle-tables', to: 'queue-claims', label: 'dispatch', tone: 'process', reveal: 2.45 },
	{ id: 'queue-runner', from: 'queue-claims', to: 'job-runner', tone: 'process', reveal: 2.45 },
	{ id: 'runner-stream', from: 'job-runner', to: 'stream-lane', tone: 'process', reveal: 2.45 },
	{ id: 'runner-batch', from: 'job-runner', to: 'batch-lane', tone: 'process', reveal: 2.45 },
	{ id: 'stream-docs', from: 'stream-lane', to: 'documents', tone: 'process', reveal: 2.45 },
	{ id: 'batch-docs', from: 'batch-lane', to: 'documents', tone: 'process', reveal: 2.45 },
	{ id: 'docs-analysis', from: 'documents', to: 'analysis', label: 'extracted artifacts', tone: 'process', reveal: 2.45 },
	{ id: 'docs-corpus', from: 'documents', to: 'corpus-index', label: 'hash + provenance', tone: 'process', reveal: 2.45 },
	{ id: 'corpus-r2', from: 'corpus-index', to: 'r2-corpus', label: 'object keys', tone: 'store', reveal: 2.45 },
	{ id: 'analysis-core', from: 'analysis', to: 'core-tables', label: 'summary + topics', tone: 'process', reveal: 2.45 },
	{ id: 'facade-repos', from: 'db-facade', to: 'repositories', tone: 'store', reveal: 2.45 },
	{ id: 'repos-fastapi', from: 'repositories', to: 'fastapi', label: 'domain reads', tone: 'store', reveal: 2.45 },
	{ id: 'fastapi-routes', from: 'fastapi', to: 'api-routes', tone: 'serve', reveal: 2.45 },
	{ id: 'routes-frontend', from: 'api-routes', to: 'frontend', label: 'HTTP / JSON', tone: 'serve', reveal: 2.45 },
	{ id: 'userland-alerts', from: 'userland-store', to: 'alerts', tone: 'serve', reveal: 2.45 },
	{ id: 'core-delib', from: 'core-tables', to: 'deliberation', tone: 'serve', reveal: 2.45 },
	{ id: 'ops-fastapi', from: 'operations', to: 'fastapi', tone: 'serve', reveal: 2.45, dashed: true }
];

export const NODE_BY_ID = new Map(ATLAS_NODES.map((node) => [node.id, node]));

export function nodeTrail(id: string): AtlasNode[] {
	const trail: AtlasNode[] = [];
	let node = NODE_BY_ID.get(id);
	while (node) {
		trail.unshift(node);
		node = node.parent ? NODE_BY_ID.get(node.parent) : undefined;
	}
	return trail;
}
