import {lazy, Suspense} from 'react';
import {Navigate, Route, Routes} from 'react-router-dom';
import type {CompanyScope} from './types';

const FinalCompletionPage = lazy(() => import('./finalCompletionPage').then((module) => ({default: module.FinalCompletionPage})));
const WorkspacePage = lazy(() => import('./workspacePage').then((module) => ({default: module.WorkspacePage})));
const ExecutivePage = lazy(() => import('./executive').then((module) => ({default: module.ExecutivePage})));
const CorePage = lazy(() => import('./financePages').then((module) => ({default: module.CorePage})));
const FinancePage = lazy(() => import('./financePages').then((module) => ({default: module.FinancePage})));
const AgingPage = lazy(() => import('./financePages').then((module) => ({default: module.AgingPage})));
const CreditNotesPage = lazy(() => import('./creditNotesPage').then((module) => ({default: module.CreditNotesPage})));
const WithholdingTaxPage = lazy(() => import('./withholdingTaxPage').then((module) => ({default: module.WithholdingTaxPage})));
const ExciseTaxPage = lazy(() => import('./exciseTaxPage').then((module) => ({default: module.ExciseTaxPage})));
const ZakatIncomeTaxPage = lazy(() => import('./zakatIncomeTaxPage').then((module) => ({default: module.ZakatIncomeTaxPage})));
const BudgetPage = lazy(() => import('./financePages').then((module) => ({default: module.BudgetPage})));
const TransactionsPage = lazy(() => import('./financePages').then((module) => ({default: module.TransactionsPage})));
const TreasuryPage = lazy(() => import('./financePages').then((module) => ({default: module.TreasuryPage})));
const LeasesPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.LeasesPage})));
const AssetsPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.AssetsPage})));
const PrepaidsPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.PrepaidsPage})));
const AccrualsPage = lazy(() => import('./financeRealPages').then((module) => ({default: module.AccrualsPage})));
const ClosePage = lazy(() => import('./financePages').then((module) => ({default: module.ClosePage})));
const AssurancePage = lazy(() => import('./financePages').then((module) => ({default: module.AssurancePage})));
const CompliancePage = lazy(() => import('./financePages').then((module) => ({default: module.CompliancePage})));
const SecurityPage = lazy(() => import('./financePages').then((module) => ({default: module.SecurityPage})));
const FxPage = lazy(() => import('./financePages').then((module) => ({default: module.FxPage})));
const InventoryPage = lazy(() => import('./operationsPages').then((module) => ({default: module.InventoryPage})));
const InventoryTraceabilityPage = lazy(() => import('./inventoryTraceabilityPage').then((module) => ({default: module.InventoryTraceabilityPage})));
const OperationalControlsPage = lazy(() => import('./operationalControlsPage').then((module) => ({default: module.OperationalControlsPage})));
const CommercePage = lazy(() => import('./operationsPages').then((module) => ({default: module.CommercePage})));
const SalesPage = lazy(() => import('./salesPage').then((module) => ({default: module.SalesPage})));
const PurchasesPage = lazy(() => import('./purchasesPage').then((module) => ({default: module.PurchasesPage})));
const MaintenancePage = lazy(() => import('./maintenancePage').then((module) => ({default: module.MaintenancePage})));
const FleetPage = lazy(() => import('./fleetPage').then((module) => ({default: module.FleetPage})));
const LegalPage = lazy(() => import('./legalPage').then((module) => ({default: module.LegalPage})));
const CipProjectsPage = lazy(() => import('./cipProjectsPage').then((module) => ({default: module.CipProjectsPage})));
const ManualJournalsPage = lazy(() => import('./manualJournalsPage').then((module) => ({default: module.ManualJournalsPage})));
const UsersPage = lazy(() => import('./usersPage').then((module) => ({default: module.UsersPage})));
const ReportsCenterPage = lazy(() => import('./reportsCenterPage').then((module) => ({default: module.ReportsCenterPage})));
const GymPage = lazy(() => import('./operationsPages').then((module) => ({default: module.GymPage})));
const RestaurantPage = lazy(() => import('./operationsPages').then((module) => ({default: module.RestaurantPage})));
const ManufacturingPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.ManufacturingPage})));
const QualityPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.QualityPage})));
const FoodSafetyPage = lazy(() => import('./operationsPages').then((module) => ({default: module.FoodSafetyPage})));
const HrPage = lazy(() => import('./operationsPages').then((module) => ({default: module.HrPage})));
const CrmPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.CrmPage})));
const AuditPage = lazy(() => import('./governancePages').then((module) => ({default: module.AuditPage})));
const ItPage = lazy(() => import('./operationsRealPages').then((module) => ({default: module.ItPage})));
const AccessGovernancePage = lazy(() => import('./governancePages').then((module) => ({default: module.AccessGovernancePage})));

export function DashboardRoutes({ar, companyId, scope}: {ar: boolean; companyId: number; scope: CompanyScope}) {
  return <Suspense fallback={<div className="route-loading">{ar ? 'جارٍ تحميل الوحدة...' : 'Loading module...'}</div>}><Routes>
    <Route path="/workbench" element={<WorkspacePage ar={ar} companyId={companyId}/>}/>
    <Route path="/finalCompletion" element={<FinalCompletionPage ar={ar} companyId={companyId}/>}/>
    <Route path="/executive" element={<ExecutivePage ar={ar} companyId={scope} apiCompanyId={companyId}/>}/>
    <Route path="/core" element={<CorePage ar={ar} companyId={companyId}/>}/>
    <Route path="/finance" element={<FinancePage ar={ar} companyId={companyId}/>}/>
    <Route path="/aging" element={<AgingPage ar={ar} companyId={companyId}/>}/>
    <Route path="/returns" element={<CreditNotesPage ar={ar} companyId={companyId}/>}/>
    <Route path="/withholdingTax" element={<WithholdingTaxPage ar={ar} companyId={companyId}/>}/>
    <Route path="/exciseTax" element={<ExciseTaxPage ar={ar} companyId={companyId}/>}/>
    <Route path="/zakatIncomeTax" element={<ZakatIncomeTaxPage ar={ar} companyId={companyId}/>}/>
    <Route path="/budget" element={<BudgetPage ar={ar} companyId={companyId}/>}/>
    <Route path="/transactions" element={<TransactionsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/inventory" element={<InventoryPage ar={ar} companyId={companyId}/>}/>
    <Route path="/inventoryTraceability" element={<InventoryTraceabilityPage ar={ar} companyId={companyId}/>}/>
    <Route path="/operationalControls" element={<OperationalControlsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/commerce" element={<CommercePage ar={ar} companyId={companyId}/>}/>
    <Route path="/sales" element={<SalesPage ar={ar} companyId={companyId}/>}/>
    <Route path="/purchases" element={<PurchasesPage ar={ar} companyId={companyId}/>}/>
    <Route path="/maintenance" element={<MaintenancePage ar={ar} companyId={companyId}/>}/>
    <Route path="/fleet" element={<FleetPage ar={ar} companyId={companyId}/>}/>
    <Route path="/legal" element={<LegalPage ar={ar} companyId={companyId}/>}/>
    <Route path="/cipProjects" element={<CipProjectsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/manualJournals" element={<ManualJournalsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/users" element={<UsersPage ar={ar} companyId={companyId}/>}/>
    <Route path="/reports" element={<ReportsCenterPage ar={ar} companyId={companyId}/>}/>
    <Route path="/crm" element={<CrmPage ar={ar} companyId={companyId}/>}/>
    <Route path="/treasury" element={<TreasuryPage ar={ar} companyId={companyId}/>}/>
    <Route path="/leases" element={<LeasesPage ar={ar} companyId={companyId}/>}/>
    <Route path="/assets" element={<AssetsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/prepaids" element={<PrepaidsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/accruals" element={<AccrualsPage ar={ar} companyId={companyId}/>}/>
    <Route path="/gym" element={<GymPage ar={ar} companyId={companyId}/>}/>
    <Route path="/restaurant" element={<RestaurantPage ar={ar} companyId={companyId}/>}/>
    <Route path="/manufacturing" element={<ManufacturingPage ar={ar} companyId={companyId}/>}/>
    <Route path="/quality" element={<QualityPage ar={ar} companyId={companyId}/>}/>
    <Route path="/foodSafety" element={<FoodSafetyPage ar={ar} companyId={companyId}/>}/>
    <Route path="/hr" element={<HrPage ar={ar} companyId={companyId}/>}/>
    <Route path="/close" element={<ClosePage ar={ar} companyId={companyId}/>}/>
    <Route path="/assurance" element={<AssurancePage ar={ar} companyId={companyId}/>}/>
    <Route path="/compliance" element={<CompliancePage ar={ar} companyId={companyId}/>}/>
    <Route path="/security" element={<SecurityPage ar={ar} companyId={companyId}/>}/>
    <Route path="/accessGovernance" element={<AccessGovernancePage ar={ar} companyId={companyId}/>}/>
    <Route path="/fx" element={<FxPage ar={ar} companyId={companyId}/>}/>
    <Route path="/audit" element={<AuditPage ar={ar} companyId={companyId}/>}/>
    <Route path="/it" element={<ItPage ar={ar} companyId={companyId}/>}/>
    <Route path="*" element={<Navigate to="/executive" replace/>}/>
  </Routes></Suspense>;
}
