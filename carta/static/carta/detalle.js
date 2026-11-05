/* Ventana del detalle del producto (decisión 34). Agregar lo sigue haciendo el formulario HTMX de carta.js. */
(() => {
    'use strict';
    const DURACION = 300;
    const UMBRAL_ARRASTRE = 110;
    const origenes = new WeakMap();
    const demora = () => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : DURACION);

    const abrir = (detalle, origen) => {
        if (!detalle || detalle.open) return;
        origenes.set(detalle, origen);
        detalle.querySelector('.detalle__desplazable').scrollTop = 0;
        detalle.showModal();
        document.body.classList.add('modal-abierto');
        requestAnimationFrame(() => requestAnimationFrame(() => { if (detalle.open) detalle.classList.add('visible'); }));
    };

    const cerrar = detalle => {
        if (!detalle.open || detalle.dataset.cerrando) return;
        detalle.dataset.cerrando = '1';
        detalle.classList.remove('visible', 'arrastrando');
        detalle.style.transform = '';
        setTimeout(() => detalle.close(), demora());
    };

    document.addEventListener('click', event => {
        const boton = event.target.closest('[data-abrir-detalle]');
        if (boton) { abrir(document.getElementById(boton.dataset.abrirDetalle), boton); return; }
        const detalle = event.target.closest('dialog.detalle');
        if (!detalle) return;
        if (event.target.closest('.detalle__asa')) {
            if (detalle.dataset.arrastro) delete detalle.dataset.arrastro;
            else cerrar(detalle);
            return;
        }
        // Un clic sobre el velo llega al <dialog> mismo, con coordenadas fuera de la ventana.
        if (event.target !== detalle) return;
        const r = detalle.getBoundingClientRect();
        if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) cerrar(detalle);
    });

    // cancel (Esc) y close no burbujean: se escuchan en la fase de captura.
    document.addEventListener('cancel', event => {
        if (!event.target.matches?.('dialog.detalle')) return;
        event.preventDefault();
        cerrar(event.target);
    }, true);

    document.addEventListener('close', event => {
        const detalle = event.target;
        if (!detalle.matches?.('dialog.detalle')) return;
        delete detalle.dataset.cerrando;
        detalle.classList.remove('visible', 'arrastrando');
        detalle.style.transform = '';
        // Si se cerró porque se agregó, el carrito ya está abierto encima: no se le quita el foco.
        if (document.querySelector('dialog[open]')) return;
        document.body.classList.remove('modal-abierto');
        origenes.get(detalle)?.focus({preventScroll: true});
    }, true);

    let arrastre = null;
    document.addEventListener('pointerdown', event => {
        const asa = event.target.closest('.detalle__asa');
        if (!asa || event.button !== 0) return;
        const detalle = asa.closest('dialog.detalle');
        delete detalle.dataset.arrastro;
        arrastre = {detalle, inicio: event.clientY, distancia: 0};
        asa.setPointerCapture(event.pointerId);
        detalle.classList.add('arrastrando');
    });
    document.addEventListener('pointermove', event => {
        if (!arrastre) return;
        arrastre.distancia = Math.max(0, event.clientY - arrastre.inicio);
        arrastre.detalle.style.transform = `translateY(${arrastre.distancia}px)`;
    });
    const soltar = () => {
        if (!arrastre) return;
        const {detalle, distancia} = arrastre;
        arrastre = null;
        detalle.classList.remove('arrastrando');
        if (distancia <= 4) { detalle.style.transform = ''; return; }
        detalle.dataset.arrastro = '1';
        if (distancia > UMBRAL_ARRASTRE) cerrar(detalle);
        else detalle.style.transform = '';
    };
    document.addEventListener('pointerup', soltar);
    document.addEventListener('pointercancel', soltar);

    // Opción obligatoria sin elegir: el aviso queda bajo su grupo, dentro de la ventana. El servidor la rechaza igual.
    document.addEventListener('invalid', event => {
        const grupo = event.target.closest('dialog.detalle .grupo-opcion');
        if (!grupo) return;
        event.preventDefault();
        if (grupo.querySelector('.error-opcion')) return;
        const nombre = grupo.querySelector('legend').textContent.split('·')[0].trim();
        const aviso = document.createElement('p');
        aviso.className = 'error-opcion';
        aviso.setAttribute('role', 'alert');
        aviso.textContent = `Elige una opción de ${nombre}.`;
        grupo.append(aviso);
        if (grupo === grupo.closest('.detalle__cuerpo').querySelector('.grupo-opcion:has(:invalid)')) {
            grupo.scrollIntoView({block: 'center', behavior: demora() ? 'smooth' : 'auto'});
        }
    }, true);
    document.addEventListener('change', event => {
        event.target.closest('.grupo-opcion')?.querySelector('.error-opcion')?.remove();
    });
})();
