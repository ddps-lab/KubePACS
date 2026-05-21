
export default function Home() {
  return (
    <div className="w-full">
      <header className="sticky top-0 z-50 w-full flex justify-center border-b border-black/10 bg-white/95 backdrop-blur-[8px]">
        <div className="flex h-14 w-full max-w-7xl items-center px-4">
          <div className="mr-4 flex items-center">
            <a href="#" className="mr-6 flex items-center gap-2">
              <img src="/logo_ddps_light.svg" alt="DDPS Logo" className="h-7 w-auto opacity-90" />
              <span className="font-light text-gray-400">|</span>
              <span className="bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text font-[Outfit] text-2xl font-bold text-transparent">KubePACS</span>
            </a>
            <nav className="hidden items-center gap-6 text-sm font-medium md:flex">
              <a href="#" className="text-slate-900/60 transition-colors hover:text-slate-900/80">Home</a>
              <a href="#about" className="text-slate-900/60 transition-colors hover:text-slate-900/80">Challenges</a>
              <a href="#architecture" className="text-slate-900/60 transition-colors hover:text-slate-900/80">Architecture</a>
            </nav>
          </div>
          <div className="flex flex-1 items-center justify-end gap-2">
            <a href="https://github.com/ddps-lab/kubepacs" target="_blank" rel="noreferrer" className="inline-flex h-9 w-9 items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-slate-900/10">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path></svg>
              <span className="sr-only">GitHub</span>
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 md:px-8">
        <main>
        <section className="relative overflow-hidden px-4 py-24 text-center md:py-32 lg:py-40">
          <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[800px] w-[1000px] -translate-x-1/2 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.15)_0%,rgba(59,130,246,0.15)_50%,transparent_70%)] blur-[80px]"></div>

          <h1 className="mx-auto mb-8 max-w-5xl font-[Outfit] text-4xl font-black leading-[1.1] tracking-tight text-slate-900 sm:text-5xl md:text-6xl">
            Performant & <br className="hidden sm:block" />
            Highly Available & Cost Efficient <br />
            <span className="relative mt-2 inline-block">
              <span className="relative z-10 bg-gradient-to-r from-blue-600 via-sky-500 to-cyan-400 bg-clip-text pb-2 pr-2 text-transparent">Spot Instances</span>
              <svg className="absolute -bottom-1 left-0 -z-10 w-full" viewBox="0 0 200 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 9Q50 2 100 5T200 8" stroke="url(#paint0_linear)" strokeWidth="6" strokeLinecap="round"/><defs><linearGradient id="paint0_linear" x1="0" y1="0" x2="200" y2="0" gradientUnits="userSpaceOnUse"><stop stopColor="#DBEAFE"/><stop offset="1" stopColor="#CFFAFE"/></linearGradient></defs></svg>
            </span>
            <span className="text-slate-800"> for Kubernetes</span>
          </h1>

          {/* <div className="mx-auto mb-8 inline-flex items-center gap-2 rounded-full border border-sky-200/50 bg-sky-50/80 px-5 py-2 text-[0.95rem] font-semibold text-sky-700 shadow-sm backdrop-blur-md transition-all hover:-translate-y-0.5 hover:shadow">
            <span className="text-xl">🎉</span>
            <span>Accepted on 27th ACM International Middleware Conference (Middleware 2026)</span>
          </div> */}

          <p className="mx-auto mb-10 max-w-3xl text-lg font-medium leading-[1.7] text-slate-500 md:text-xl">
            KubePACS is a Kubernetes-native spot instance provisioning system that constructs node pools optimized for both <strong className="font-semibold text-slate-800">cost and performance</strong> while guaranteeing <strong className="font-semibold text-slate-800">high availability</strong>. It redefines cloud resource allocation by maximizing performance-per-dollar utilizing real-time cloud datasets.
          </p>

          <div className="flex flex-col items-center justify-center gap-4 sm:flex-row sm:gap-6">
            <a href="https://arxiv.org/abs/2604.24027" target="_blank" rel="noreferrer" className="group flex w-full items-center justify-center gap-2 rounded-full bg-slate-900 px-8 py-4 text-[1.05rem] font-semibold text-white shadow-xl shadow-slate-900/10 transition-all hover:-translate-y-1 hover:bg-slate-800 hover:shadow-2xl hover:shadow-slate-900/20 sm:w-auto">
              <svg className="transition-transform group-hover:-translate-y-0.5" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              Read Paper (PDF)
            </a>
            <a href="https://github.com/ddps-lab/kubepacs" target="_blank" rel="noreferrer" className="group flex w-full items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-8 py-4 text-[1.05rem] font-semibold text-slate-800 shadow-sm transition-all hover:-translate-y-1 hover:border-sky-200 hover:bg-sky-50 hover:text-sky-700 hover:shadow-md hover:shadow-sky-100 sm:w-auto">
              <svg className="transition-transform group-hover:drop-shadow-sm" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path></svg>
              View on GitHub
            </a>
          </div>
        </section>

        <section id="about" className="py-24">
          <h2 className="mb-12 text-center font-[Outfit] text-3xl font-bold text-slate-900 md:text-5xl">Key Challenges</h2>
          <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
            <div className="group relative overflow-hidden rounded-[24px] border border-white/50 bg-gradient-to-br from-white/90 to-white/40 p-8 shadow-[0_4px_20px_rgba(0,0,0,0.03)] backdrop-blur-lg transition-all duration-500 hover:-translate-y-2 hover:border-sky-500/30 hover:shadow-[0_20px_40px_rgba(14,165,233,0.12)] sm:p-10">
              <div className="mb-6 inline-flex rounded-2xl border border-white/50 bg-gradient-to-br from-sky-500/15 to-violet-600/5 p-4 text-sky-600 transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
              </div>
              <h3 className="mb-4 font-[Outfit] text-xl font-semibold text-slate-900 md:text-2xl">Performance Heterogeneity</h3>
              <p className="leading-relaxed text-slate-600">
                Cloud instances often vary vastly in computing power, yet traditional tools scale nodes based merely on static CPU/memory requirements without accounting for benchmark performance variation.
              </p>
            </div>
            <div className="group relative overflow-hidden rounded-[24px] border border-white/50 bg-gradient-to-br from-white/90 to-white/40 p-8 shadow-[0_4px_20px_rgba(0,0,0,0.03)] backdrop-blur-lg transition-all duration-500 hover:-translate-y-2 hover:border-sky-500/30 hover:shadow-[0_20px_40px_rgba(14,165,233,0.12)] sm:p-10">
              <div className="mb-6 inline-flex rounded-2xl border border-white/50 bg-gradient-to-br from-sky-500/15 to-violet-600/5 p-4 text-sky-600 transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              </div>
              <h3 className="mb-4 font-[Outfit] text-xl font-semibold text-slate-900 md:text-2xl">Inadequate Single-Node Metrics</h3>
              <p className="leading-relaxed text-slate-600">
                Existing approaches infer cluster-level availability from single-node placement scores, exposing multi-node workloads to high interruption risks. KubePACS utilizes Multi-Node SPS.
              </p>
            </div>
             <div className="group relative overflow-hidden rounded-[24px] border border-white/50 bg-gradient-to-br from-white/90 to-white/40 p-8 shadow-[0_4px_20px_rgba(0,0,0,0.03)] backdrop-blur-lg transition-all duration-500 hover:-translate-y-2 hover:border-sky-500/30 hover:shadow-[0_20px_40px_rgba(14,165,233,0.12)] sm:p-10">
              <div className="mb-6 inline-flex rounded-2xl border border-white/50 bg-gradient-to-br from-sky-500/15 to-violet-600/5 p-4 text-sky-600 transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110">
                 <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg>
              </div>
              <h3 className="mb-4 font-[Outfit] text-xl font-semibold text-slate-900 md:text-2xl">Lack of Workload Awareness</h3>
              <p className="leading-relaxed text-slate-600">
                Spot price alone decoupled from hardware capability makes it challenging to select ideal nodes for specialized workloads (e.g., Disk/Network I/O bound tasks).
              </p>
            </div>
          </div>
        </section>

        <section id="architecture" className="py-24">
          <div className="mb-16 text-center">
            <h2 className="mb-4 font-[Outfit] text-3xl font-bold text-slate-900 md:text-5xl">How KubePACS Works</h2>
            <h3 className="mb-4 text-2xl font-semibold text-slate-900">
              Multi-Objective Optimization Pipeline
            </h3>
            <p className="mx-auto max-w-3xl text-lg leading-relaxed text-slate-600">
              KubePACS solves the complex multi-objective optimization problem to build the perfect cluster. It seamlessly integrates real-time cloud datasets into a three-stage automated pipeline.
            </p>
          </div>
          
          <div className="flex flex-col items-stretch justify-between gap-6 rounded-[24px] border border-black/5 bg-white/80 p-8 backdrop-blur-md md:flex-row md:p-12">
            <div className="group relative flex flex-1 flex-col rounded-2xl border border-white/50 bg-white/70 p-8 text-left shadow-[0_4px_15px_rgba(0,0,0,0.02)] transition-all hover:-translate-y-1 hover:border-sky-500/30 hover:bg-white hover:shadow-[0_15px_35px_rgba(14,165,233,0.1)] md:p-10">
              <div className="absolute right-6 top-4 font-[Outfit] text-6xl font-extrabold leading-none text-sky-500/10 transition-colors group-hover:text-sky-500/20">01</div>
              <div className="relative z-10 mt-8">
                <h3 className="mb-4 text-xl font-bold text-slate-900">Metric Preprocessor</h3>
                <p className="text-[0.95rem] leading-relaxed text-slate-600">Aggregates spot prices, benchmark scores (CoreMark), and multi-node SPS, scaling performance for workload-specific I/O capabilities.</p>
              </div>
            </div>
            
            <div className="flex h-12 w-12 shrink-0 self-center items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-sky-600 md:rotate-0 rotate-90">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
            </div>

            <div className="group relative flex flex-1 flex-col rounded-2xl border border-white/50 bg-white/70 p-8 text-left shadow-[0_4px_15px_rgba(0,0,0,0.02)] transition-all hover:-translate-y-1 hover:border-sky-500/30 hover:bg-white hover:shadow-[0_15px_35px_rgba(14,165,233,0.1)] md:p-10">
              <div className="absolute right-6 top-4 font-[Outfit] text-6xl font-extrabold leading-none text-sky-500/10 transition-colors group-hover:text-sky-500/20">02</div>
              <div className="relative z-10 mt-8">
                <h3 className="mb-4 text-xl font-bold text-slate-900">ILP Node Selection Solver</h3>
                <p className="text-[0.95rem] leading-relaxed text-slate-600">Formulates an Integer Linear Programming (ILP) problem to balance cost performance and avoid over-allocation while satisfying demand.</p>
              </div>
            </div>

            <div className="flex h-12 w-12 shrink-0 self-center items-center justify-center rounded-full border border-sky-500/20 bg-sky-500/10 text-sky-600 md:rotate-0 rotate-90">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
            </div>

            <div className="group relative flex flex-1 flex-col rounded-2xl border border-white/50 bg-white/70 p-8 text-left shadow-[0_4px_15px_rgba(0,0,0,0.02)] transition-all hover:-translate-y-1 hover:border-sky-500/30 hover:bg-white hover:shadow-[0_15px_35px_rgba(14,165,233,0.1)] md:p-10">
              <div className="absolute right-6 top-4 font-[Outfit] text-6xl font-extrabold leading-none text-sky-500/10 transition-colors group-hover:text-sky-500/20">03</div>
              <div className="relative z-10 mt-8">
                <h3 className="mb-4 text-xl font-bold text-slate-900">GSS Optimizer</h3>
                <p className="text-[0.95rem] leading-relaxed text-slate-600">Iteratively applies the Golden Section Search (GSS) algorithm to efficiently identify the optimal cost-performance trade-off hyperparameter (α).</p>
              </div>
            </div>
          </div>
        </section>


      </main>
      </div>

      <footer className="mt-auto border-t border-black/10 py-16 text-center text-slate-500 w-full mb-0 pb-16">
        <div className="mb-4 inline-block font-[Outfit] text-xl font-bold text-slate-900">KubePACS</div>
        <p className="text-sm">&copy; {new Date().getFullYear()} HYU DDPS Lab. All rights reserved.</p>
      </footer>
    </div>
  );
}
