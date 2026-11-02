/**
 * Correo (capacidad "correo" -> /api/v1/correo/*). Espejo de `src/api/routers/correo.py`: bandeja
 * unificada (Gmail solo lectura + circulares/encuestas internas), detalle, reenvío, respuesta
 * AUTENTICADA (sin contraseña — reutiliza la identidad del token JWT, paralelo de
 * `confirmar_lectura`/`responder_encuesta` de escritorio que siguen reservados al escenario de
 * terminal compartido), compositor básico (Nuevo mensaje/Nueva encuesta) con Para/CC/Cco real, y
 * las 5 carpetas reales (Borradores/Programados/Papelera/Pospuestos/Importantes) + Enviados — el
 * usuario reconsideró el recorte original (ver commits previos) citando que Gmail real ofrece las
 * mismas carpetas en móvil y escritorio: aquí se construye la paridad completa.
 *
 * Compromisos honestos de esta ronda (documentados, no ocultados):
 *   - El selector de fecha/hora de "Programar"/"Posponer" es un par de `TextInput` (AAAA-MM-DD /
 *     HH:MM) en vez de un date-picker nativo: no existe ningún date-picker ya instalado en
 *     `package.json` y añadir una dependencia nueva solo para esto no se justificaba.
 *   - Gmail sigue siendo sync de solo lectura: no tiene Borradores/Programados (no hay "redactar"),
 *     igual que en escritorio; sí tiene Papelera/Pospuestos/Importantes (carpetas locales reales).
 */
import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {
  bandeja,
  borradores,
  cancelarProgramacion,
  circularDetalle,
  crearCircular,
  crearEncuesta,
  eliminarBorrador,
  encuestaDetalle,
  enviados,
  gmailDetalle,
  guardarBorradorCircular,
  guardarBorradorEncuesta,
  importantes,
  marcarImportante,
  marcarLeidoCircular,
  marcarLeidoEncuesta,
  marcarLeidoGmail,
  moverPapelera,
  papelera,
  posponer,
  pospuestos,
  programados,
  programarCircular,
  programarEncuesta,
  publicarBorradorCircular,
  publicarBorradorEncuesta,
  reenviarCircular,
  reenviarEncuesta,
  responderCircular,
  responderEncuesta,
  restaurarDePapelera,
  sugerenciasDestinatarios,
  type CircularDetalle,
  type DestinatarioEntrada,
  type EncuestaDetalle,
  type GmailDetalle,
  type MensajeBandeja,
  type RespuestaPregunta,
  type SugerenciaDestinatario,
  type TipoMensaje,
  type TipoPregunta,
} from '@/api/correo';
import {colors} from '@/theme/colors';
import type {CorreoProps} from '@/navigation/types';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Vista = 'lista' | 'detalle' | 'componer';
type TipoNuevo = 'circular' | 'encuesta';
type TipoDestino = 'PARA' | 'CC' | 'CCO';
type Carpeta =
  | 'recibidos'
  | 'enviados'
  | 'borradores'
  | 'programados'
  | 'papelera'
  | 'pospuestos'
  | 'importantes';

interface ReenviarInfo {
  tipo: 'circular' | 'encuesta';
  id: number;
}

interface BorradorInfo {
  tipo: 'circular' | 'encuesta';
  id: number;
}

interface RespuestaLocal {
  opciones: number[];
  otro: string;
  texto: string;
}

// Pregunta del COMPOSITOR de encuesta (estado local, mientras se edita) — espejo simplificado de
// `_PreguntaEditorWidget` de escritorio (`circulares_gui.py`): texto + tipo (OPCIONES/TEXTO) +
// opciones (solo relevantes si tipo es OPCIONES). La opción "Otro" es SIEMPRE implícita en la
// respuesta (no se guarda aquí, ver aviso bajo la lista de opciones), igual que en escritorio.
interface PreguntaCompuesta {
  texto: string;
  tipo: TipoPregunta;
  opciones: string[];
}

const PREGUNTA_VACIA = (): PreguntaCompuesta => ({texto: '', tipo: 'OPCIONES', opciones: ['', '']});

const CARPETAS: {key: Carpeta; labelKey: string; label: string}[] = [
  {key: 'recibidos', labelKey: 'correo.carpeta_recibidos', label: 'Recibidos'},
  {key: 'enviados', labelKey: 'correo.carpeta_enviados', label: 'Enviados'},
  {key: 'borradores', labelKey: 'correo.carpeta_borradores', label: 'Borradores'},
  {key: 'programados', labelKey: 'correo.carpeta_programados', label: 'Programados'},
  {key: 'papelera', labelKey: 'correo.carpeta_papelera', label: 'Papelera'},
  {key: 'pospuestos', labelKey: 'correo.carpeta_pospuestos', label: 'Pospuestos'},
  {key: 'importantes', labelKey: 'correo.carpeta_importantes', label: 'Importantes'},
];

const CARGADORES: Record<Carpeta, () => Promise<MensajeBandeja[]>> = {
  recibidos: bandeja,
  enviados,
  borradores,
  programados,
  papelera,
  pospuestos,
  importantes,
};

function iconoTipo(tipo: MensajeBandeja['tipo']): string {
  if (tipo === 'circular') return '📢';
  if (tipo === 'encuesta') return '📊';
  return '✉️';
}

function etiquetaDestinatario(d: DestinatarioEntrada, t: (key: string, def: string, opts?: Record<string, unknown>) => string): string {
  if ('usuario_id' in d) return d.nombre || t('correo.usuario_num', 'Usuario #{{n}}', {n: d.usuario_id});
  if ('centro_codigo' in d) return t('correo.centro_lbl', '🏢 Centro {{c}}', {c: d.centro_codigo});
  return d.nombre || d.email_externo;
}

export default function CorreoScreen({navigation}: CorreoProps) {
  const {t} = useTranslation();
  const [vista, setVista] = useState<Vista>('lista');
  const [carpeta, setCarpeta] = useState<Carpeta>('recibidos');
  const [cargando, setCargando] = useState(true);
  const [mensajes, setMensajes] = useState<MensajeBandeja[]>([]);
  const [aviso, setAviso] = useState<{ok: boolean; texto: string} | null>(null);

  // Detalle del mensaje abierto.
  const [seleccionado, setSeleccionado] = useState<MensajeBandeja | null>(null);
  const [detalleGmail, setDetalleGmail] = useState<GmailDetalle | null>(null);
  const [detalleCircular, setDetalleCircular] = useState<CircularDetalle | null>(null);
  const [detalleEncuesta, setDetalleEncuesta] = useState<EncuestaDetalle | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [accionando, setAccionando] = useState(false);

  // Responder (identidad ya autenticada, sin contraseña).
  const [comentarioRespuesta, setComentarioRespuesta] = useState('');
  const [respuestasEncuesta, setRespuestasEncuesta] = useState<Record<number, RespuestaLocal>>({});
  const [enviandoRespuesta, setEnviandoRespuesta] = useState(false);

  // Posponer (Recibidos) — fecha/hora en TextInput (sin date-picker instalado, ver docstring).
  const [posponiendo, setPosponiendo] = useState(false);
  const [fechaPosponer, setFechaPosponer] = useState('');
  const [horaPosponer, setHoraPosponer] = useState('');

  // Compositor (Nuevo mensaje/Nueva encuesta, Reenviar, reabrir Borrador, Programar).
  const [reenviarInfo, setReenviarInfo] = useState<ReenviarInfo | null>(null);
  const [borradorInfo, setBorradorInfo] = useState<BorradorInfo | null>(null);
  const [tipoNuevo, setTipoNuevo] = useState<TipoNuevo>('circular');
  const [titulo, setTitulo] = useState('');
  const [cuerpo, setCuerpo] = useState('');
  const [preguntas, setPreguntas] = useState<PreguntaCompuesta[]>([PREGUNTA_VACIA()]);
  const [destinatarios, setDestinatarios] = useState<DestinatarioEntrada[]>([]);
  const [tipoDestino, setTipoDestino] = useState<TipoDestino>('PARA');
  const [textoBusqueda, setTextoBusqueda] = useState('');
  const [sugerencias, setSugerencias] = useState<SugerenciaDestinatario[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [modoProgramar, setModoProgramar] = useState(false);
  const [fechaProg, setFechaProg] = useState('');
  const [horaProg, setHoraProg] = useState('');

  const cargarLista = useCallback(async (c: Carpeta) => {
    setCargando(true);
    try {
      setMensajes(await CARGADORES[c]());
    } catch {
      setMensajes([]);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarLista(carpeta);
  }, [cargarLista, carpeta]);

  const cambiarCarpeta = useCallback((c: Carpeta) => {
    setCarpeta(c);
    setAviso(null);
  }, []);

  // Autocompletado de destinatarios: mismo criterio de 3 orígenes que el servidor ya resuelve
  // tenant-safe (interno/centro/externo) — aquí solo se pinta, con un pequeño debounce.
  useEffect(() => {
    if (!textoBusqueda.trim()) {
      setSugerencias([]);
      return;
    }
    let vivo = true;
    const timer = setTimeout(async () => {
      const r = await sugerenciasDestinatarios(textoBusqueda);
      if (vivo) {
        setSugerencias(r);
      }
    }, 250);
    return () => {
      vivo = false;
      clearTimeout(timer);
    };
  }, [textoBusqueda]);

  const sugerenciasConExterno = useMemo(() => {
    const texto = textoBusqueda.trim();
    if (!EMAIL_RE.test(texto)) return sugerencias;
    const yaExiste = sugerencias.some(
      s => s.origen === 'externo' && s.identidad.email_externo === texto,
    );
    if (yaExiste) return sugerencias;
    return [
      ...sugerencias,
      {
        origen: 'externo' as const,
        icono: '✉️',
        texto,
        tooltip: t('correo.nuevo_contacto_externo', 'Nuevo contacto externo'),
        identidad: {email_externo: texto},
      },
    ];
  }, [sugerencias, textoBusqueda, t]);

  const reiniciarRespuesta = useCallback(() => {
    setComentarioRespuesta('');
    setRespuestasEncuesta({});
    setPosponiendo(false);
    setFechaPosponer('');
    setHoraPosponer('');
  }, []);

  const abrirMensaje = useCallback(async (item: MensajeBandeja) => {
    setSeleccionado(item);
    setVista('detalle');
    setDetalleGmail(null);
    setDetalleCircular(null);
    setDetalleEncuesta(null);
    reiniciarRespuesta();
    setCargandoDetalle(true);
    try {
      if (item.tipo === 'gmail') {
        setDetalleGmail(await gmailDetalle(item.id));
      } else if (item.tipo === 'circular') {
        setDetalleCircular(await circularDetalle(item.id));
      } else {
        setDetalleEncuesta(await encuestaDetalle(item.id));
      }
      // Marcar leído solo tiene sentido viniendo de Recibidos (mismo criterio que escritorio:
      // `_cargar_bandeja_unificada` es la única que llama a `marcar_leido_*`).
      if (carpeta === 'recibidos') {
        if (item.tipo === 'gmail') {
          await marcarLeidoGmail(item.id);
        } else if (item.tipo === 'circular') {
          await marcarLeidoCircular(item.id);
        } else {
          await marcarLeidoEncuesta(item.id);
        }
        setMensajes(prev => prev.map(m => (m.tipo === item.tipo && m.id === item.id
          ? {...m, leido: true}
          : m)));
      }
    } finally {
      setCargandoDetalle(false);
    }
  }, [carpeta, reiniciarRespuesta]);

  const reiniciarCompositor = useCallback(() => {
    setTitulo('');
    setCuerpo('');
    setPreguntas([PREGUNTA_VACIA()]);
    setDestinatarios([]);
    setTipoDestino('PARA');
    setTextoBusqueda('');
    setSugerencias([]);
    setReenviarInfo(null);
    setBorradorInfo(null);
    setModoProgramar(false);
    setFechaProg('');
    setHoraProg('');
  }, []);

  const abrirNuevo = useCallback((tipo: TipoNuevo) => {
    reiniciarCompositor();
    setTipoNuevo(tipo);
    setVista('componer');
    setAviso(null);
  }, [reiniciarCompositor]);

  const abrirReenviar = useCallback((tipo: 'circular' | 'encuesta', id: number) => {
    reiniciarCompositor();
    setReenviarInfo({tipo, id});
    setVista('componer');
    setAviso(null);
  }, [reiniciarCompositor]);

  // Reabrir un BORRADOR para seguir editando (Borradores) — precarga título/cuerpo/destinatarios
  // reales desde el detalle completo (mismo dato que ya trae `circularDetalle`/`encuestaDetalle`).
  const abrirBorrador = useCallback(async (item: MensajeBandeja) => {
    reiniciarCompositor();
    setTipoNuevo(item.tipo === 'encuesta' ? 'encuesta' : 'circular');
    setBorradorInfo({tipo: item.tipo === 'encuesta' ? 'encuesta' : 'circular', id: item.id});
    setVista('componer');
    setAviso(null);
    setCargandoDetalle(true);
    try {
      const dest = (d: {usuario_id: number | null; usuario_nombre: string | null; tipo: string}[]) =>
        d
          .filter(x => x.usuario_id != null)
          .map(x => ({
            usuario_id: x.usuario_id as number,
            nombre: x.usuario_nombre || undefined,
            tipo: (x.tipo as TipoDestino) || 'PARA',
          }));
      if (item.tipo === 'encuesta') {
        const d = await encuestaDetalle(item.id);
        if (d) {
          setTitulo(d.titulo || '');
          setCuerpo(d.intro || '');
          setPreguntas(d.preguntas.length
            ? d.preguntas.map(p => ({
                texto: p.texto,
                tipo: p.tipo,
                // Si el borrador tenía OPCIONES sin opciones guardadas (caso límite), se ofrecen 2
                // vacías como arranque — mismo mínimo por defecto que el compositor de escritorio.
                opciones: p.opciones.length
                  ? p.opciones.map(op => op.texto)
                  : (p.tipo === 'OPCIONES' ? ['', ''] : []),
              }))
            : [PREGUNTA_VACIA()]);
          setDestinatarios(dest(d.destinatarios));
        }
      } else {
        const d = await circularDetalle(item.id);
        if (d) {
          setTitulo(d.titulo || '');
          setCuerpo(d.cuerpo || '');
          setDestinatarios(dest(d.destinatarios));
        }
      }
    } finally {
      setCargandoDetalle(false);
    }
  }, [reiniciarCompositor]);

  const agregarDestinatario = useCallback((s: SugerenciaDestinatario) => {
    let entrada: DestinatarioEntrada;
    if (s.origen === 'usuario') {
      entrada = {
        usuario_id: Number(s.identidad.usuario_id),
        nombre: s.identidad.nombre as string | undefined,
        tipo: tipoDestino,
      };
    } else if (s.origen === 'centro') {
      entrada = {centro_codigo: String(s.identidad.centro_codigo), tipo: tipoDestino};
    } else {
      entrada = {
        email_externo: String(s.identidad.email_externo),
        nombre: s.identidad.nombre as string | undefined,
        tipo: tipoDestino,
      };
    }
    setDestinatarios(prev => [...prev, entrada]);
    setTextoBusqueda('');
    setSugerencias([]);
  }, [tipoDestino]);

  const quitarDestinatario = useCallback((idx: number) => {
    setDestinatarios(prev => prev.filter((_, i) => i !== idx));
  }, []);

  const actualizarPregunta = useCallback((idx: number, texto: string) => {
    setPreguntas(prev => prev.map((p, i) => (i === idx ? {...p, texto} : p)));
  }, []);

  // Alterna OPCIONES/TEXTO para una pregunta — al pasar a OPCIONES sin opciones previas, arranca
  // con 2 vacías (mismo mínimo por defecto que `_PreguntaEditorWidget` de escritorio).
  const actualizarTipoPregunta = useCallback((idx: number, tipo: TipoPregunta) => {
    setPreguntas(prev => prev.map((p, i) => (i === idx
      ? {...p, tipo, opciones: tipo === 'OPCIONES' && !p.opciones.length ? ['', ''] : p.opciones}
      : p)));
  }, []);

  const actualizarOpcion = useCallback((idx: number, idxOpcion: number, texto: string) => {
    setPreguntas(prev => prev.map((p, i) => (i === idx
      ? {...p, opciones: p.opciones.map((o, j) => (j === idxOpcion ? texto : o))}
      : p)));
  }, []);

  const agregarOpcion = useCallback((idx: number) => {
    setPreguntas(prev => prev.map((p, i) => (i === idx ? {...p, opciones: [...p.opciones, '']} : p)));
  }, []);

  const quitarOpcion = useCallback((idx: number, idxOpcion: number) => {
    setPreguntas(prev => prev.map((p, i) => (i === idx
      ? {...p, opciones: p.opciones.filter((_, j) => j !== idxOpcion)}
      : p)));
  }, []);

  const preguntasValidas = useCallback(
    () => preguntas
      .map(p => ({
        texto: p.texto.trim(),
        tipo: p.tipo,
        opciones: p.opciones.map(o => o.trim()).filter(Boolean),
      }))
      .filter(p => Boolean(p.texto)),
    [preguntas],
  );

  const volverALista = useCallback(async () => {
    setVista('lista');
    await cargarLista(carpeta);
  }, [cargarLista, carpeta]);

  const enviar = useCallback(async () => {
    setAviso(null);
    if (reenviarInfo) {
      if (!destinatarios.length) {
        setAviso({ok: false, texto: t('correo.anade_destinatario', 'Añade al menos un destinatario.')});
        return;
      }
      setEnviando(true);
      try {
        const r = reenviarInfo.tipo === 'circular'
          ? await reenviarCircular(reenviarInfo.id, destinatarios)
          : await reenviarEncuesta(reenviarInfo.id, destinatarios);
        if (r.ok) {
          setAviso({ok: true, texto: t('correo.reenviado_ok', 'Reenviado correctamente.')});
          await volverALista();
        } else {
          setAviso({ok: false, texto: r.error || t('correo.no_se_pudo_reenviar', 'No se pudo reenviar.')});
        }
      } catch {
        setAviso({ok: false, texto: t('correo.sin_conexion', 'No hay conexión con el servidor.')});
      } finally {
        setEnviando(false);
      }
      return;
    }
    if (!titulo.trim()) {
      setAviso({ok: false, texto: t('correo.indica_titulo', 'Indica un título.')});
      return;
    }
    if (!destinatarios.some(d => d.tipo === 'PARA')) {
      setAviso({ok: false, texto: t('correo.indica_destinatario_para', 'Indica al menos un destinatario en «Para».')});
      return;
    }
    // Programar envío (fecha/hora obligatorias en este modo).
    if (modoProgramar) {
      if (!fechaProg.trim() || !horaProg.trim()) {
        setAviso({ok: false, texto: t('correo.indica_fecha_hora_envio', 'Indica fecha (AAAA-MM-DD) y hora (HH:MM) de envío.')});
        return;
      }
      setEnviando(true);
      try {
        const fecha_programada = `${fechaProg.trim()}T${horaProg.trim()}`;
        const r = tipoNuevo === 'circular'
          ? await programarCircular({
              id_circular_borrador: borradorInfo?.tipo === 'circular' ? borradorInfo.id : undefined,
              titulo: titulo.trim(), cuerpo, fecha_programada, destinatarios,
            })
          : await programarEncuesta({
              id_encuesta_borrador: borradorInfo?.tipo === 'encuesta' ? borradorInfo.id : undefined,
              titulo: titulo.trim(), intro: cuerpo, preguntas: preguntasValidas(),
              fecha_programada, destinatarios,
            });
        if (r.ok) {
          setAviso({ok: true, texto: t('correo.envio_programado_ok', 'Envío programado.')});
          await volverALista();
        } else {
          setAviso({ok: false, texto: r.error || t('correo.no_se_pudo_programar', 'No se pudo programar.')});
        }
      } catch {
        setAviso({ok: false, texto: t('correo.sin_conexion', 'No hay conexión con el servidor.')});
      } finally {
        setEnviando(false);
      }
      return;
    }
    // Publicar un borrador existente, o crear uno nuevo directamente.
    setEnviando(true);
    try {
      let r;
      if (borradorInfo) {
        r = borradorInfo.tipo === 'circular'
          ? await publicarBorradorCircular(borradorInfo.id, {titulo: titulo.trim(), cuerpo, destinatarios})
          : await publicarBorradorEncuesta(borradorInfo.id, {
              titulo: titulo.trim(), intro: cuerpo, preguntas: preguntasValidas(), destinatarios,
            });
      } else {
        r = tipoNuevo === 'circular'
          ? await crearCircular({titulo: titulo.trim(), cuerpo, destinatarios})
          : await crearEncuesta({titulo: titulo.trim(), intro: cuerpo, preguntas: preguntasValidas(), destinatarios});
      }
      if (r.ok) {
        setAviso({ok: true, texto: tipoNuevo === 'circular' ? t('correo.circular_enviada', 'Circular enviada.') : t('correo.encuesta_enviada', 'Encuesta enviada.')});
        await volverALista();
      } else {
        setAviso({ok: false, texto: r.error || t('correo.no_se_pudo_enviar', 'No se pudo enviar.')});
      }
    } catch {
      setAviso({ok: false, texto: t('correo.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [reenviarInfo, destinatarios, titulo, cuerpo, preguntas, tipoNuevo, borradorInfo, modoProgramar,
      fechaProg, horaProg, preguntasValidas, volverALista, t]);

  const guardarComoBorrador = useCallback(async () => {
    setAviso(null);
    if (!titulo.trim() && !cuerpo.trim()) {
      setAviso({ok: false, texto: t('correo.escribe_titulo_o_cuerpo', 'Escribe al menos un título o un cuerpo para guardar el borrador.')});
      return;
    }
    setEnviando(true);
    try {
      const r = tipoNuevo === 'circular'
        ? await guardarBorradorCircular({
            id_circular: borradorInfo?.tipo === 'circular' ? borradorInfo.id : undefined,
            titulo: titulo.trim(), cuerpo, destinatarios,
          })
        : await guardarBorradorEncuesta({
            id_encuesta: borradorInfo?.tipo === 'encuesta' ? borradorInfo.id : undefined,
            titulo: titulo.trim(), intro: cuerpo, preguntas: preguntasValidas(), destinatarios,
          });
      if (r.ok) {
        setAviso({ok: true, texto: t('correo.borrador_guardado_ok', 'Borrador guardado.')});
        await volverALista();
      } else {
        setAviso({ok: false, texto: r.error || t('correo.no_se_pudo_guardar_borrador', 'No se pudo guardar el borrador.')});
      }
    } catch {
      setAviso({ok: false, texto: t('correo.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [titulo, cuerpo, tipoNuevo, borradorInfo, destinatarios, preguntasValidas, volverALista, t]);

  const eliminarBorradorActual = useCallback(async () => {
    if (!borradorInfo) return;
    setEnviando(true);
    try {
      const r = await eliminarBorrador(borradorInfo.tipo, borradorInfo.id);
      if (r.ok) {
        setAviso({ok: true, texto: t('correo.borrador_eliminado_ok', 'Borrador eliminado.')});
        await volverALista();
      } else {
        setAviso({ok: false, texto: r.error || t('correo.no_se_pudo_eliminar', 'No se pudo eliminar.')});
      }
    } catch {
      setAviso({ok: false, texto: t('correo.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviando(false);
    }
  }, [borradorInfo, volverALista, t]);

  // ── Responder (identidad ya autenticada, sin contraseña) ────────────────────────────────────
  const toggleOpcionEncuesta = useCallback((idPregunta: number, idOpcion: number) => {
    setRespuestasEncuesta(prev => {
      const actual = prev[idPregunta] || {opciones: [], otro: '', texto: ''};
      const tiene = actual.opciones.includes(idOpcion);
      return {
        ...prev,
        [idPregunta]: {
          ...actual,
          opciones: tiene ? actual.opciones.filter(o => o !== idOpcion) : [...actual.opciones, idOpcion],
        },
      };
    });
  }, []);

  const setOtroEncuesta = useCallback((idPregunta: number, texto: string) => {
    setRespuestasEncuesta(prev => ({
      ...prev,
      [idPregunta]: {...(prev[idPregunta] || {opciones: [], otro: '', texto: ''}), otro: texto},
    }));
  }, []);

  const setTextoEncuesta = useCallback((idPregunta: number, texto: string) => {
    setRespuestasEncuesta(prev => ({
      ...prev,
      [idPregunta]: {...(prev[idPregunta] || {opciones: [], otro: '', texto: ''}), texto},
    }));
  }, []);

  const responder = useCallback(async () => {
    if (!seleccionado) return;
    setEnviandoRespuesta(true);
    setAviso(null);
    try {
      let r;
      if (seleccionado.tipo === 'circular') {
        r = await responderCircular(seleccionado.id, comentarioRespuesta);
      } else {
        const payload: Record<number, RespuestaPregunta> = {};
        Object.entries(respuestasEncuesta).forEach(([pid, v]) => {
          payload[Number(pid)] = {opciones: v.opciones, otro: v.otro, texto: v.texto};
        });
        r = await responderEncuesta(seleccionado.id, payload, comentarioRespuesta);
      }
      if (r.ok) {
        setAviso({ok: true, texto: t('correo.respuesta_enviada_ok', 'Respuesta enviada.')});
        setVista('lista');
        await cargarLista(carpeta);
      } else {
        setAviso({ok: false, texto: r.error || t('correo.no_se_pudo_responder', 'No se pudo responder.')});
      }
    } catch {
      setAviso({ok: false, texto: t('correo.sin_conexion', 'No hay conexión con el servidor.')});
    } finally {
      setEnviandoRespuesta(false);
    }
  }, [seleccionado, comentarioRespuesta, respuestasEncuesta, carpeta, cargarLista, t]);

  // ── Acciones de carpeta sobre el mensaje abierto (mismo set que `_fila_acciones_carpeta` de
  // escritorio, aplicado al detalle abierto en vez de a una fila seleccionada) ───────────────────
  const accionCarpeta = useCallback(async (
    accion: 'importante' | 'quitar_importante' | 'papelera' | 'restaurar' | 'cancelar',
  ) => {
    if (!seleccionado) return;
    setAccionando(true);
    try {
      let ok = false;
      if (accion === 'importante' || accion === 'quitar_importante') {
        ok = await marcarImportante(seleccionado.tipo, seleccionado.id, accion === 'importante');
      } else if (accion === 'papelera') {
        ok = await moverPapelera(seleccionado.tipo, seleccionado.id);
      } else if (accion === 'restaurar') {
        ok = await restaurarDePapelera(seleccionado.tipo, seleccionado.id);
      } else if (accion === 'cancelar' && seleccionado.tipo !== 'gmail') {
        const r = await cancelarProgramacion(seleccionado.tipo, seleccionado.id);
        ok = r.ok;
      }
      if (ok) {
        setAviso({ok: true, texto: t('correo.hecho_ok', 'Hecho.')});
        setVista('lista');
        await cargarLista(carpeta);
      } else {
        setAviso({ok: false, texto: t('correo.no_se_pudo_completar_accion', 'No se pudo completar la acción.')});
      }
    } finally {
      setAccionando(false);
    }
  }, [seleccionado, carpeta, cargarLista, t]);

  const confirmarPosponer = useCallback(async () => {
    if (!seleccionado) return;
    if (!fechaPosponer.trim() || !horaPosponer.trim()) {
      setAviso({ok: false, texto: t('correo.indica_fecha_hora', 'Indica fecha (AAAA-MM-DD) y hora (HH:MM).')});
      return;
    }
    setAccionando(true);
    try {
      const ok = await posponer(
        seleccionado.tipo, seleccionado.id, `${fechaPosponer.trim()}T${horaPosponer.trim()}`,
      );
      if (ok) {
        setAviso({ok: true, texto: t('correo.pospuesto_ok', 'Pospuesto.')});
        setVista('lista');
        await cargarLista(carpeta);
      } else {
        setAviso({ok: false, texto: t('correo.no_se_pudo_posponer', 'No se pudo posponer.')});
      }
    } finally {
      setAccionando(false);
    }
  }, [seleccionado, fechaPosponer, horaPosponer, carpeta, cargarLista, t]);

  const tituloCabecera = vista === 'lista'
    ? t('correo.titulo', 'Correo')
    : vista === 'detalle'
      ? (seleccionado ? `${iconoTipo(seleccionado.tipo)} ${seleccionado.asunto_o_titulo}` : t('correo.mensaje_titulo', 'Mensaje'))
      : reenviarInfo
        ? t('correo.reenviar_titulo', 'Reenviar')
        : borradorInfo
          ? (tipoNuevo === 'circular' ? t('correo.editar_borrador_titulo', 'Editar borrador') : t('correo.editar_borrador_encuesta_titulo', 'Editar borrador (encuesta)'))
          : tipoNuevo === 'circular' ? t('correo.nueva_circular_titulo', 'Nueva circular') : t('correo.nueva_encuesta_titulo', 'Nueva encuesta');

  const volver = useCallback(() => {
    if (vista === 'lista') {
      navigation.goBack();
    } else {
      setVista('lista');
      setAviso(null);
    }
  }, [vista, navigation]);

  const esRecibidos = carpeta === 'recibidos';
  const esPapelera = carpeta === 'papelera';
  const esProgramados = carpeta === 'programados';
  const esImportantes = carpeta === 'importantes';
  const puedeResponder = seleccionado && seleccionado.tipo !== 'gmail' && !esPapelera && !esProgramados;

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={volver}>
          <Text style={styles.back}>‹ {vista === 'lista' ? t('common.volver_sin_flecha', 'Volver') : t('correo.titulo', 'Correo')}</Text>
        </TouchableOpacity>
        <Text style={styles.title} numberOfLines={1}>{tituloCabecera}</Text>
        <View style={{width: 90}} />
      </View>

      {vista === 'lista' && (
        <>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.tabsRow}
            contentContainerStyle={styles.tabsContent}>
            {CARPETAS.map(c => (
              <TouchableOpacity
                key={c.key}
                style={[styles.tab, carpeta === c.key && styles.tabActivo]}
                onPress={() => cambiarCarpeta(c.key)}>
                <Text style={[styles.tabTexto, carpeta === c.key && styles.tabTextoActivo]}>
                  {t(c.labelKey, c.label)}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          <View style={styles.accionesRow}>
            <TouchableOpacity style={styles.accionBtn} onPress={() => abrirNuevo('circular')}>
              <Text style={styles.accionBtnTexto}>+ {t('correo.nuevo_mensaje_btn', 'Nuevo mensaje')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.accionBtn} onPress={() => abrirNuevo('encuesta')}>
              <Text style={styles.accionBtnTexto}>+ {t('correo.nueva_encuesta_btn', 'Nueva encuesta')}</Text>
            </TouchableOpacity>
          </View>
          {cargando ? (
            <ActivityIndicator color={colors.cyan} size="large" style={{marginTop: 40}} />
          ) : (
            <FlatList
              data={mensajes}
              keyExtractor={item => `${item.tipo}-${item.id}`}
              contentContainerStyle={styles.form}
              ListEmptyComponent={<Text style={styles.hint}>{t('correo.sin_mensajes_carpeta', 'Sin mensajes en esta carpeta.')}</Text>}
              renderItem={({item}) => (
                <TouchableOpacity
                  style={styles.card}
                  onPress={() => (carpeta === 'borradores' ? abrirBorrador(item) : abrirMensaje(item))}>
                  <Text style={[styles.cardTitle, !item.leido && styles.cardTitleNoLeido]}>
                    {iconoTipo(item.tipo)} {item.asunto_o_titulo}
                  </Text>
                  <Text style={styles.cardDetail}>
                    {item.remitente_o_emisor} · {(item.fecha || '—').slice(0, 16)}
                  </Text>
                </TouchableOpacity>
              )}
            />
          )}
        </>
      )}

      {vista === 'detalle' && (
        <ScrollView contentContainerStyle={styles.form}>
          {cargandoDetalle ? (
            <ActivityIndicator color={colors.cyan} size="large" style={{marginTop: 40}} />
          ) : detalleGmail ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>{detalleGmail.asunto || t('correo.sin_asunto', '(sin asunto)')}</Text>
              <Text style={styles.cardDetail}>
                {t('correo.de_lbl', 'De: {{r}} · {{f}}', {r: detalleGmail.remitente, f: detalleGmail.fecha || '—'})}
              </Text>
              <Text style={[styles.cardDetail, styles.cuerpo]}>
                {detalleGmail.cuerpo || t('correo.sin_contenido', '(sin contenido)')}
              </Text>
            </View>
          ) : detalleCircular ? (
            <>
              <View style={styles.card}>
                <Text style={styles.cardTitle}>📢 {detalleCircular.titulo}</Text>
                <Text style={styles.cardDetail}>
                  {detalleCircular.creador_nombre} · {detalleCircular.creado}
                </Text>
                <Text style={[styles.cardDetail, styles.cuerpo]}>{detalleCircular.cuerpo}</Text>
              </View>
              <TouchableOpacity
                style={styles.button}
                onPress={() => abrirReenviar('circular', detalleCircular.id)}>
                <Text style={styles.buttonText}>{t('correo.reenviar_titulo', 'Reenviar')}</Text>
              </TouchableOpacity>
            </>
          ) : detalleEncuesta ? (
            <>
              <View style={styles.card}>
                <Text style={styles.cardTitle}>📊 {detalleEncuesta.titulo}</Text>
                <Text style={styles.cardDetail}>
                  {detalleEncuesta.creador_nombre} · {detalleEncuesta.creado}
                </Text>
                <Text style={[styles.cardDetail, styles.cuerpo]}>{detalleEncuesta.intro}</Text>
              </View>
              {detalleEncuesta.preguntas.map(p => (
                <View key={p.id} style={styles.repuestoRow}>
                  <Text style={[styles.cardDetail, {marginBottom: 8}]}>{p.texto}</Text>
                  {p.tipo === 'TEXTO' ? (
                    <TextInput
                      style={styles.input}
                      placeholder={t('correo.tu_respuesta_ph', 'Tu respuesta…')}
                      placeholderTextColor={colors.textDim}
                      value={respuestasEncuesta[p.id]?.texto || ''}
                      onChangeText={texto => setTextoEncuesta(p.id, texto)}
                    />
                  ) : (
                    <>
                      {p.opciones.map(op => {
                        const activo = (respuestasEncuesta[p.id]?.opciones || []).includes(op.id);
                        return (
                          <TouchableOpacity
                            key={op.id}
                            style={[styles.chip, activo && styles.chipActivo, {marginBottom: 6, alignSelf: 'flex-start'}]}
                            onPress={() => toggleOpcionEncuesta(p.id, op.id)}>
                            <Text style={[styles.chipTexto, activo && styles.chipTextoActivo]}>
                              {activo ? '☑ ' : '☐ '}{op.texto}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                      <TextInput
                        style={styles.input}
                        placeholder={t('correo.otro_especificar_ph', 'Otro (especificar)…')}
                        placeholderTextColor={colors.textDim}
                        value={respuestasEncuesta[p.id]?.otro || ''}
                        onChangeText={texto => setOtroEncuesta(p.id, texto)}
                      />
                    </>
                  )}
                </View>
              ))}
              <TouchableOpacity
                style={styles.button}
                onPress={() => abrirReenviar('encuesta', detalleEncuesta.id)}>
                <Text style={styles.buttonText}>{t('correo.reenviar_titulo', 'Reenviar')}</Text>
              </TouchableOpacity>
            </>
          ) : (
            <Text style={styles.hint}>{t('correo.no_se_pudo_cargar_mensaje', 'No se pudo cargar el mensaje.')}</Text>
          )}

          {!cargandoDetalle && puedeResponder && (
            <>
              <Text style={styles.sectionTitle}>{t('correo.tu_comentario_opc_h2', 'Tu comentario (opcional)')}</Text>
              <TextInput
                style={[styles.input, {minHeight: 70}]}
                placeholder={t('correo.anade_comentario_ph', 'Añade un comentario…')}
                placeholderTextColor={colors.textDim}
                multiline
                value={comentarioRespuesta}
                onChangeText={setComentarioRespuesta}
              />
              <TouchableOpacity
                style={[styles.button, styles.buttonFull, enviandoRespuesta && styles.buttonDisabled]}
                onPress={responder}
                disabled={enviandoRespuesta}>
                {enviandoRespuesta ? (
                  <ActivityIndicator color={colors.bg} />
                ) : (
                  <Text style={styles.buttonText}>✉️ {t('correo.responder_btn', 'Responder')}</Text>
                )}
              </TouchableOpacity>
            </>
          )}

          {!cargandoDetalle && seleccionado && (
            <View style={styles.accionesCarpeta}>
              {esRecibidos && (
                <>
                  <TouchableOpacity style={styles.accionBtn} onPress={() => accionCarpeta('importante')}>
                    <Text style={styles.accionBtnTexto}>⭐ {t('correo.importante_btn', 'Importante')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.accionBtn}
                    onPress={() => setPosponiendo(v => !v)}>
                    <Text style={styles.accionBtnTexto}>⏰ {t('correo.posponer_btn', 'Posponer')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.accionBtn, styles.accionBtnDanger]}
                    onPress={() => accionCarpeta('papelera')}>
                    <Text style={[styles.accionBtnTexto, styles.accionBtnTextoDanger]}>🗑 {t('correo.papelera_btn', 'Papelera')}</Text>
                  </TouchableOpacity>
                </>
              )}
              {esPapelera && (
                <TouchableOpacity style={styles.accionBtn} onPress={() => accionCarpeta('restaurar')}>
                  <Text style={styles.accionBtnTexto}>♻ {t('correo.restaurar_btn', 'Restaurar')}</Text>
                </TouchableOpacity>
              )}
              {esProgramados && seleccionado.tipo !== 'gmail' && (
                <TouchableOpacity
                  style={[styles.accionBtn, styles.accionBtnDanger]}
                  onPress={() => accionCarpeta('cancelar')}>
                  <Text style={[styles.accionBtnTexto, styles.accionBtnTextoDanger]}>
                    ✖ {t('correo.cancelar_programacion_btn', 'Cancelar programación')}
                  </Text>
                </TouchableOpacity>
              )}
              {esImportantes && (
                <TouchableOpacity style={styles.accionBtn} onPress={() => accionCarpeta('quitar_importante')}>
                  <Text style={styles.accionBtnTexto}>⭐ {t('correo.quitar_importante_btn', 'Quitar importante')}</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          {posponiendo && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>{t('correo.posponer_hasta_h2', 'Posponer hasta')}</Text>
              <TextInput
                style={styles.input}
                placeholder={t('correo.fecha_formato_ph', 'AAAA-MM-DD')}
                placeholderTextColor={colors.textDim}
                value={fechaPosponer}
                onChangeText={setFechaPosponer}
              />
              <TextInput
                style={styles.input}
                placeholder={t('correo.hora_formato_ph', 'HH:MM')}
                placeholderTextColor={colors.textDim}
                value={horaPosponer}
                onChangeText={setHoraPosponer}
              />
              <TouchableOpacity
                style={[styles.button, accionando && styles.buttonDisabled]}
                onPress={confirmarPosponer}
                disabled={accionando}>
                <Text style={styles.buttonText}>{t('common.confirmar', 'Confirmar')}</Text>
              </TouchableOpacity>
            </View>
          )}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}
        </ScrollView>
      )}

      {vista === 'componer' && (
        <ScrollView contentContainerStyle={styles.form}>
          {!reenviarInfo && (
            <>
              <Text style={styles.sectionTitle}>{t('correo.titulo_h2', 'Título')}</Text>
              <TextInput
                style={styles.input}
                placeholder={t('correo.titulo_ph', 'Título')}
                placeholderTextColor={colors.textDim}
                value={titulo}
                onChangeText={setTitulo}
              />
              <Text style={styles.sectionTitle}>
                {tipoNuevo === 'circular' ? t('correo.mensaje_h2', 'Mensaje') : t('correo.introduccion_h2', 'Introducción')}
              </Text>
              <TextInput
                style={[styles.input, {minHeight: 80}]}
                placeholder={tipoNuevo === 'circular' ? t('correo.escribe_mensaje_ph', 'Escribe el mensaje…') : t('correo.introduccion_opc_ph', 'Introducción (opcional)')}
                placeholderTextColor={colors.textDim}
                multiline
                value={cuerpo}
                onChangeText={setCuerpo}
              />
              {tipoNuevo === 'encuesta' && (
                <>
                  <Text style={styles.sectionTitle}>{t('correo.preguntas_h2', 'Preguntas')}</Text>
                  {preguntas.map((p, idx) => (
                    <View key={idx} style={styles.card}>
                      <TextInput
                        style={styles.input}
                        placeholder={t('correo.pregunta_num_ph', 'Pregunta {{n}}', {n: idx + 1})}
                        placeholderTextColor={colors.textDim}
                        value={p.texto}
                        onChangeText={texto => actualizarPregunta(idx, texto)}
                      />
                      <View style={styles.chipsRow}>
                        <TouchableOpacity
                          style={[styles.chip, p.tipo === 'OPCIONES' && styles.chipActivo]}
                          onPress={() => actualizarTipoPregunta(idx, 'OPCIONES')}>
                          <Text style={[styles.chipTexto, p.tipo === 'OPCIONES' && styles.chipTextoActivo]}>
                            ☑ {t('correo.opciones_lbl', 'Opciones')}
                          </Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={[styles.chip, p.tipo === 'TEXTO' && styles.chipActivo]}
                          onPress={() => actualizarTipoPregunta(idx, 'TEXTO')}>
                          <Text style={[styles.chipTexto, p.tipo === 'TEXTO' && styles.chipTextoActivo]}>
                            ✏️ {t('correo.texto_libre_lbl', 'Texto libre')}
                          </Text>
                        </TouchableOpacity>
                      </View>
                      {p.tipo === 'OPCIONES' && (
                        <>
                          {p.opciones.map((op, idxOpcion) => (
                            <View key={idxOpcion} style={styles.opcionRow}>
                              <TextInput
                                style={[styles.input, styles.opcionInput]}
                                placeholder={t('correo.opcion_num_ph', 'Opción {{n}}', {n: idxOpcion + 1})}
                                placeholderTextColor={colors.textDim}
                                value={op}
                                onChangeText={texto => actualizarOpcion(idx, idxOpcion, texto)}
                              />
                              <TouchableOpacity onPress={() => quitarOpcion(idx, idxOpcion)}>
                                <Text style={styles.opcionQuitar}>✕</Text>
                              </TouchableOpacity>
                            </View>
                          ))}
                          <TouchableOpacity onPress={() => agregarOpcion(idx)}>
                            <Text style={styles.link}>+ {t('correo.anadir_opcion_btn', 'Añadir opción')}</Text>
                          </TouchableOpacity>
                          <Text style={styles.hintOtro}>
                            ℹ {t('correo.otro_auto', 'La opción «Otro» (con texto libre) se ofrece siempre al responder.')}
                          </Text>
                        </>
                      )}
                    </View>
                  ))}
                  <TouchableOpacity onPress={() => setPreguntas(prev => [...prev, PREGUNTA_VACIA()])}>
                    <Text style={styles.link}>+ {t('correo.anadir_pregunta_btn', 'Añadir pregunta')}</Text>
                  </TouchableOpacity>
                </>
              )}
            </>
          )}

          <Text style={styles.sectionTitle}>{t('correo.destinatarios_h2', 'Destinatarios')}</Text>
          <View style={styles.chipsRow}>
            {(['PARA', 'CC', 'CCO'] as TipoDestino[]).map(td => (
              <TouchableOpacity
                key={td}
                style={[styles.chip, tipoDestino === td && styles.chipActivo]}
                onPress={() => setTipoDestino(td)}>
                <Text style={[styles.chipTexto, tipoDestino === td && styles.chipTextoActivo]}>
                  {td}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <TextInput
            style={styles.input}
            placeholder={t('correo.nombre_email_centro_ph', 'Nombre, email o centro…')}
            placeholderTextColor={colors.textDim}
            value={textoBusqueda}
            onChangeText={setTextoBusqueda}
          />
          {sugerenciasConExterno.length > 0 && (
            <View style={styles.sugerenciasBox}>
              {sugerenciasConExterno.slice(0, 8).map((s, i) => (
                <TouchableOpacity
                  key={`${s.origen}-${i}`}
                  style={styles.sugerenciaItem}
                  onPress={() => agregarDestinatario(s)}>
                  <Text style={styles.sugerenciaTexto}>{s.icono} {s.texto}</Text>
                  <Text style={styles.sugerenciaTooltip}>{s.tooltip}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
          {destinatarios.length > 0 && (
            <View style={styles.chipsRow}>
              {destinatarios.map((d, idx) => (
                <TouchableOpacity
                  key={idx}
                  style={styles.chipDestinatario}
                  onPress={() => quitarDestinatario(idx)}>
                  <Text style={styles.chipTexto}>
                    {d.tipo} · {etiquetaDestinatario(d, t)} ✕
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {!reenviarInfo && (
            <>
              <TouchableOpacity
                style={styles.linkRow}
                onPress={() => setModoProgramar(v => !v)}>
                <Text style={styles.link}>
                  {modoProgramar ? `✕ ${t('correo.cancelar_programacion_envio', 'Cancelar programación de envío')}` : `🕒 ${t('correo.programar_envio', 'Programar envío')}`}
                </Text>
              </TouchableOpacity>
              {modoProgramar && (
                <View style={styles.card}>
                  <Text style={styles.sectionTitle}>{t('correo.enviar_el_h2', 'Enviar el')}</Text>
                  <TextInput
                    style={styles.input}
                    placeholder={t('correo.fecha_formato_ph', 'AAAA-MM-DD')}
                    placeholderTextColor={colors.textDim}
                    value={fechaProg}
                    onChangeText={setFechaProg}
                  />
                  <TextInput
                    style={styles.input}
                    placeholder={t('correo.hora_formato_ph', 'HH:MM')}
                    placeholderTextColor={colors.textDim}
                    value={horaProg}
                    onChangeText={setHoraProg}
                  />
                </View>
              )}
            </>
          )}

          {aviso ? <Text style={aviso.ok ? styles.ok : styles.error}>{aviso.texto}</Text> : null}

          {!reenviarInfo && !modoProgramar && (
            <TouchableOpacity
              style={[styles.button, enviando && styles.buttonDisabled]}
              onPress={guardarComoBorrador}
              disabled={enviando}>
              <Text style={styles.buttonText}>📝 {t('correo.guardar_borrador_btn', 'Guardar borrador')}</Text>
            </TouchableOpacity>
          )}
          {borradorInfo && !modoProgramar && (
            <TouchableOpacity
              style={[styles.button, styles.buttonDanger, enviando && styles.buttonDisabled]}
              onPress={eliminarBorradorActual}
              disabled={enviando}>
              <Text style={styles.buttonText}>🗑 {t('correo.eliminar_borrador_btn', 'Eliminar borrador')}</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[styles.button, styles.buttonFull, enviando && styles.buttonDisabled]}
            onPress={enviar}
            disabled={enviando}>
            {enviando ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.buttonText}>
                {reenviarInfo
                  ? t('correo.reenviar_titulo', 'Reenviar')
                  : modoProgramar
                    ? t('correo.programar_btn', 'Programar')
                    : borradorInfo ? t('correo.publicar_btn', 'Publicar') : t('correo.enviar_btn', 'Enviar')}
              </Text>
            )}
          </TouchableOpacity>
        </ScrollView>
      )}

      {aviso && vista === 'lista' ? (
        <Text style={[aviso.ok ? styles.ok : styles.error, {marginHorizontal: 16}]}>
          {aviso.texto}
        </Text>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  back: {color: colors.cyan, fontSize: 16, fontWeight: '700', width: 90},
  title: {color: colors.text, fontSize: 18, fontWeight: '800', flex: 1, textAlign: 'center'},
  tabsRow: {flexGrow: 0, marginBottom: 4},
  tabsContent: {paddingHorizontal: 16, gap: 8},
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabActivo: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  tabTexto: {color: colors.textDim, fontSize: 13, fontWeight: '700'},
  tabTextoActivo: {color: colors.bg},
  accionesRow: {flexDirection: 'row', gap: 8, paddingHorizontal: 16, marginTop: 10, marginBottom: 8},
  accionBtn: {
    flex: 1,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
  },
  accionBtnDanger: {borderColor: colors.danger},
  accionBtnTexto: {color: colors.cyan, fontWeight: '700', fontSize: 13},
  accionBtnTextoDanger: {color: colors.danger},
  accionesCarpeta: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10},
  form: {padding: 16, paddingBottom: 32},
  sectionTitle: {color: colors.text, fontWeight: '800', fontSize: 14, marginTop: 14, marginBottom: 8},
  hint: {color: colors.textDim, textAlign: 'center', fontSize: 14, marginTop: 20},
  input: {
    backgroundColor: colors.panel,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    marginBottom: 8,
  },
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  cardTitle: {color: colors.text, fontWeight: '700', fontSize: 15},
  cardTitleNoLeido: {fontWeight: '900'},
  cardDetail: {color: colors.textDim, marginTop: 4, fontSize: 12},
  cuerpo: {marginTop: 10, fontSize: 13, lineHeight: 19},
  repuestoRow: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginBottom: 6,
  },
  link: {color: colors.cyan, fontWeight: '700', fontSize: 12, marginTop: 4, marginBottom: 8},
  opcionRow: {flexDirection: 'row', alignItems: 'center', gap: 8},
  opcionInput: {flex: 1},
  opcionQuitar: {color: colors.danger, fontSize: 16, fontWeight: '900', paddingHorizontal: 6},
  hintOtro: {color: colors.textDim, fontSize: 11, marginTop: 2, marginBottom: 4},
  linkRow: {marginTop: 10},
  chipsRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8},
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActivo: {backgroundColor: colors.cyan, borderColor: colors.cyan},
  chipTexto: {color: colors.textDim, fontSize: 12, fontWeight: '700'},
  chipTextoActivo: {color: colors.bg},
  chipDestinatario: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: colors.panelAlt,
    borderWidth: 1,
    borderColor: colors.cyan,
  },
  sugerenciasBox: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    marginBottom: 8,
    overflow: 'hidden',
  },
  sugerenciaItem: {paddingHorizontal: 12, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: colors.border},
  sugerenciaTexto: {color: colors.text, fontSize: 13, fontWeight: '700'},
  sugerenciaTooltip: {color: colors.textDim, fontSize: 11, marginTop: 2},
  button: {
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: 'center',
    marginBottom: 8,
  },
  buttonDanger: {backgroundColor: colors.danger},
  buttonFull: {marginTop: 4},
  buttonDisabled: {opacity: 0.6},
  buttonText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginTop: 8, fontSize: 12, textAlign: 'center'},
  error: {color: colors.danger, marginTop: 8, fontSize: 12, textAlign: 'center'},
});
