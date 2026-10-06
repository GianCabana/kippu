/* HTMX transports cart POSTs; Alpine owns UI state. Payments use native POST. */
(() => {
    'use strict';
    const emitir = (nombre, detail) => window.dispatchEvent(new CustomEvent(nombre, {detail}));
    const esCarrito = event => event.detail.elt?.matches('[data-carrito-form]');
    let foco = '';
    let scroll = 0;
    document.addEventListener('htmx:beforeRequest', event => {
        if (!esCarrito(event)) return;
        const app = document.getElementById('carta-app');
        const state = window.Alpine?.$data(app);
        if (state?.pagando || state?.error) { event.preventDefault(); return; }
        foco = document.activeElement?.id || '';
        scroll = document.getElementById('carrito-contenido')?.scrollTop || 0;
        emitir('kippu-inicio');
    });
    document.addEventListener('htmx:afterSwap', event => {
        if (event.detail.target?.id !== 'carrito-datos') return;
        emitir('kippu-actualizado', {foco, scroll});
    });
    document.addEventListener('htmx:afterRequest', event => {
        if (esCarrito(event)) emitir('kippu-fin');
    });
    for (const nombre of ['htmx:responseError', 'htmx:sendError', 'htmx:timeout', 'htmx:swapError']) {
        document.addEventListener(nombre, event => {
            if (!esCarrito(event)) return;
            const status = event.detail.xhr?.status;
            emitir('kippu-error', status === 403
                ? 'Tu sesión necesita actualizarse. Recarga la carta antes de continuar.'
                : 'No pudimos confirmar el cambio. Actualiza la carta para ver el estado antes de volver a intentarlo.');
        });
    }
    document.addEventListener('alpine:init', () => {
        Alpine.data('cartaKippu', () => ({
            busqueda: '', categoria: 'todas', cantidad: 0, total: 0,
            ocupado: false, pagando: false, error: '', visible: false, cerrando: false,
            init() { this.leerTotales(); this.formatear(); this.filtrar(); },
            pesos(valor) { return new Intl.NumberFormat('es-CL', {style: 'currency', currency: 'CLP', maximumFractionDigits: 0}).format(valor); },
            leerTotales() {
                const panel = this.$root.querySelector('[data-cantidad]');
                this.cantidad = Number(panel?.dataset.cantidad || 0);
                this.total = Number(panel?.dataset.total || 0);
            },
            formatear() {
                this.$root.querySelectorAll('[data-pesos]').forEach(el => {
                    const valor = Number(el.dataset.pesos);
                    if (Number.isFinite(valor)) el.textContent = this.pesos(valor);
                });
            },
            normalizar(texto) { return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim(); },
            filtrar() {
                const consulta = this.normalizar(this.busqueda);
                let visibles = 0;
                const secciones = this.$root.querySelectorAll('.categoria-seccion');
                secciones.forEach(seccion => {
                    let cantidad = 0;
                    seccion.querySelectorAll('.producto').forEach(producto => {
                        const coincide = (this.categoria === 'todas' || this.categoria === seccion.id) && this.normalizar(producto.dataset.busqueda).includes(consulta);
                        producto.hidden = !coincide;
                        if (coincide) cantidad++;
                    });
                    seccion.hidden = cantidad === 0;
                    visibles += cantidad;
                });
                this.$root.querySelectorAll('[data-categoria]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.categoria === this.categoria)));
                this.$root.querySelector('#sin-resultados').hidden = visibles > 0 || secciones.length === 0;
            },
            elegirCategoria(valor) { this.categoria = valor; this.filtrar(); },
            limpiar() { this.busqueda = ''; this.filtrar(); this.$refs.buscar.focus(); },
            abrirCarrito() {
                const modal = this.$refs.dialogo;
                if (!modal || modal.open || this.cerrando) return;
                modal.showModal();
                document.body.classList.add('modal-abierto');
                requestAnimationFrame(() => requestAnimationFrame(() => { if (modal.open && !this.cerrando) this.visible = true; }));
            },
            cerrarCarrito() {
                if (!this.$refs.dialogo.open || this.cerrando) return;
                this.cerrando = true; this.visible = false;
                const demora = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 280;
                setTimeout(() => this.$refs.dialogo.close(), demora);
            },
            alCerrar() {
                this.visible = false; this.cerrando = false;
                document.body.classList.remove('modal-abierto');
                this.$refs.abrir?.focus({preventScroll: true});
            },
            clicFondo(event) {
                if (event.target !== this.$refs.dialogo) return;
                const r = event.target.getBoundingClientRect();
                if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) this.cerrarCarrito();
            },
            actualizarCarrito(detalle) {
                this.leerTotales(); this.formatear(); this.error = ''; this.ocupado = false;
                const abierto = this.$refs.dialogo?.open;
                this.abrirCarrito();
                this.$nextTick(() => {
                    const contenido = document.getElementById('carrito-contenido');
                    if (contenido) contenido.scrollTop = detalle.scroll;
                    if (abierto) {
                        const boton = document.getElementById(detalle.foco);
                        (boton || this.$refs.dialogo.querySelector('.cerrar'))?.focus({preventScroll: true});
                    }
                });
            },
            iniciarPago(event) {
                if (this.ocupado || this.pagando || this.error) { event.preventDefault(); return; }
                this.pagando = true;
            },
        }));
    });
})();
