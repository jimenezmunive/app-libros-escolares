import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import io
import unicodedata
import re
import requests
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Pedido de Ayuda Escolar", layout="wide", page_icon="📚")

# --- MODO PRIVADO (OCULTAR MENÚS Y MARCAS DE AGUA) ---
hide_menu_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_menu_style, unsafe_allow_html=True)

# --- CONFIGURACIÓN GOOGLE SHEETS ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🛡️ BLINDAJE: USAMOS EL ID EXACTO DEL ARCHIVO PARA NO CONFUNDIRSE DE BASE DE DATOS
# ID extraído de: https://docs.google.com/spreadsheets/d/12QNeHXx-It2u5xJUd9q66KrYs-829GnfTQafE16ZZEU/edit
SHEET_ID = "12QNeHXx-It2u5xJUd9q66KrYs-829GnfTQafE16ZZEU"

# --- LISTA ESTRICTA DE COLUMNAS (BLINDAJE DE ORDEN) ---
COLUMNAS_ESTRICTAS = [
    "ID_Pedido", "Fecha_Creacion", "Ultima_Modificacion", "Cliente", 
    "Celular", "Detalle", "Total", "Abonado", "Saldo", "Estado", 
    "Comprobante", "Comprobante2", "Historial_Cambios"
]

# --- ESTADO ---
if 'reset_manual' not in st.session_state: st.session_state.reset_manual = 0
if 'exito_cliente' not in st.session_state: st.session_state.exito_cliente = False
if 'ultimo_pedido_cliente' not in st.session_state: st.session_state.ultimo_pedido_cliente = None
if 'admin_autenticado' not in st.session_state: st.session_state.admin_autenticado = False

# --- FUNCIÓN: LIMPIEZA DE PRECIOS ---
def limpiar_moneda(valor):
    try:
        if pd.isna(valor) or str(valor).strip() == "": return 0.0
        if isinstance(valor, (int, float)): return float(valor)
        valor_str = str(valor).strip()
        valor_str = valor_str.replace('$', '').replace(' ', '').replace(',', '')
        if not valor_str: return 0.0
        return float(valor_str)
    except:
        return 0.0

# --- CONEXIÓN GOOGLE SHEETS ---
@st.cache_resource
def conectar_sheets():
    try:
        json_str = st.secrets["google_json"]
        creds_dict = json.loads(json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        return None

# --- GESTIÓN DE CONFIGURACIÓN (NEQUI) ---
def obtener_celular_nequi():
    client = conectar_sheets()
    if not client: return "No configurado"
    try:
        # 🛡️ USAMOS open_by_key PARA ASEGURAR EL ARCHIVO CORRECTO
        sh = client.open_by_key(SHEET_ID)
        try: wk = sh.worksheet("Config")
        except:
            wk = sh.add_worksheet(title="Config", rows=10, cols=2)
            wk.update([["Clave", "Valor"], ["celular_nequi", "3000000000"]])
            return "3000000000"
        
        records = wk.get_all_records()
        df_conf = pd.DataFrame(records).astype(str)
        res = df_conf[df_conf['Clave'] == 'celular_nequi']
        if not res.empty: return res.iloc[0]['Valor']
        else: return "3000000000"
    except: return "3000000000"

def guardar_celular_nequi(nuevo_numero):
    client = conectar_sheets()
    if not client: return False
    try:
        sh = client.open_by_key(SHEET_ID)
        try: wk = sh.worksheet("Config")
        except: wk = sh.add_worksheet(title="Config", rows=10, cols=2)
        wk.clear()
        wk.update([["Clave", "Valor"], ["celular_nequi", str(nuevo_numero)]])
        return True
    except: return False

# --- FUNCIONES AUXILIARES ---
def normalizar_clave(texto):
    if not isinstance(texto, str): texto = str(texto)
    texto = texto.strip().lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return texto

def limpiar_numero(num):
    return re.sub(r'\D', '', str(num))

def obtener_nuevo_id(df_pedidos):
    max_id = 0
    if not df_pedidos.empty:
        if 'ID_Pedido' in df_pedidos.columns:
            for pid in df_pedidos['ID_Pedido']:
                pid_clean = re.sub(r'\D', '', str(pid))
                if pid_clean.isdigit():
                    val = int(pid_clean)
                    if val > max_id: max_id = val
    return f"{max_id + 1:04d}"

# --- CRUD DATOS ---
def cargar_inventario():
    client = conectar_sheets()
    if not client: return pd.DataFrame()
    try:
        sh = client.open_by_key(SHEET_ID)
        wk = sh.worksheet("Inventario")
        data = wk.get_all_records()
        if not data: return pd.DataFrame(columns=["Grado", "Area", "Libro", "Costo", "Precio Venta"])
        df = pd.DataFrame(data)
        cols = ['Grado', 'Area', 'Libro']
        for col in cols: 
            if col in df.columns: df[col] = df[col].astype(str).str.strip()
        
        if 'Precio Venta' in df.columns: df['Precio Venta'] = df['Precio Venta'].apply(limpiar_moneda)
        else: df['Precio Venta'] = 0.0
        if 'Costo' in df.columns: df['Costo'] = df['Costo'].apply(limpiar_moneda)
        else: df['Costo'] = 0.0   
        return df
    except: return pd.DataFrame()

def guardar_inventario(df):
    client = conectar_sheets()
    if not client: return
    try:
        sh = client.open_by_key(SHEET_ID)
        wk = sh.worksheet("Inventario")
        df['Costo'] = df['Costo'].apply(limpiar_moneda)
        df['Precio Venta'] = df['Precio Venta'].apply(limpiar_moneda)
        df['Ganancia'] = df['Precio Venta'] - df['Costo']
        wk.clear()
        wk.update([df.columns.values.tolist()] + df.values.tolist())
        st.cache_data.clear()
    except: pass

def cargar_pedidos():
    client = conectar_sheets()
    if not client: return pd.DataFrame(columns=COLUMNAS_ESTRICTAS)
    
    try:
        sh = client.open_by_key(SHEET_ID)
        wk = sh.worksheet("Pedidos")
        data = wk.get_all_records()
        
        if not data: return pd.DataFrame(columns=COLUMNAS_ESTRICTAS)
        
        df = pd.DataFrame(data)
        
        # BLINDAJE: Asegurar columnas y orden
        for col in COLUMNAS_ESTRICTAS:
            if col not in df.columns: df[col] = ""
        df = df[COLUMNAS_ESTRICTAS]
        
        if 'ID_Pedido' in df.columns: df['ID_Pedido'] = df['ID_Pedido'].astype(str)
        return df
    except: 
        return pd.DataFrame(columns=COLUMNAS_ESTRICTAS)

def guardar_pedido_db(df):
    client = conectar_sheets()
    if not client: return
    try:
        # Forzar orden estricto antes de guardar
        for col in COLUMNAS_ESTRICTAS:
            if col not in df.columns: df[col] = ""
        df = df[COLUMNAS_ESTRICTAS]
        
        sh = client.open_by_key(SHEET_ID)
        wk = sh.worksheet("Pedidos")
        df = df.astype(str)
        wk.clear()
        wk.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e: st.error(f"Error guardando pedido: {e}")

# --- COMPONENTES VISUALES ---
def generar_link_whatsapp(celular, mensaje):
    celular = str(celular).replace(" ", "").replace("+", "").strip()
    if not celular.startswith("57"): celular = "57" + celular
    return f"https://wa.me/{celular}?text={mensaje.replace(' ', '%20').replace(chr(10), '%0A')}"

def generar_excel_matriz_bytes(df_pedidos, df_inventario):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    worksheet = workbook.add_worksheet("Listado Matriz")
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1})
    fmt_col = workbook.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'center'})
    fmt_cell = workbook.add_format({'border': 1, 'align': 'center'})
    
    current_row = 0
    grados = df_inventario['Grado'].unique()
    for grado in grados:
        inv_grado = df_inventario[df_inventario['Grado'] == grado]
        if inv_grado.empty: continue
        mapa = {normalizar_clave(k): v for k, v in zip(inv_grado['Libro'], inv_grado['Area'])}
        areas = inv_grado['Area'].unique()
        patron = f"[{grado}]"
        pedidos_grado = df_pedidos[df_pedidos['Detalle'].str.contains(patron, regex=False, na=False)].copy()
        if pedidos_grado.empty: continue

        data_rows = []
        for _, p in pedidos_grado.iterrows():
            row = {
                'Cliente': p['Cliente'], 
                'Fecha_Creacion': p.get('Fecha_Creacion', ''),
                'Ultima_Modificacion': p.get('Ultima_Modificacion', ''),
                'Celular': p['Celular'], 
                'Total': p['Total'], 
                'Saldo': p['Saldo']
            }
            for a in areas: row[a] = 0
            items = str(p['Detalle']).split(" | ")
            count = 0
            for item in items:
                if patron in item:
                    area_enc = None
                    match = re.search(r'\((.*?)\)', item)
                    if match:
                        posible = match.group(1).strip()
                        for a in areas:
                            if str(a).strip().lower() == posible.lower():
                                area_enc = a
                                break
                    if not area_enc:
                        raw = item.replace(patron, "").strip()
                        area_enc = mapa.get(normalizar_clave(raw))
                    if area_enc:
                        row[area_enc] = 1
                        count += 1
            row['Cant'] = count
            data_rows.append(row)
        if not data_rows: continue
        
        worksheet.write(current_row, 0, f"GRADO: {grado}", fmt_header)
        current_row += 1
        
        headers = ['Cliente', 'Fecha Creación', 'Últ. Modif', 'Celular', 'Total', 'Saldo'] + list(areas) + ['Cant']
        for i, h in enumerate(headers): worksheet.write(current_row, i, h, fmt_col)
        current_row += 1
        for d in data_rows:
            worksheet.write(current_row, 0, d['Cliente'], fmt_cell)
            worksheet.write(current_row, 1, d['Fecha_Creacion'], fmt_cell)
            worksheet.write(current_row, 2, d['Ultima_Modificacion'], fmt_cell)
            worksheet.write(current_row, 3, d['Celular'], fmt_cell)
            worksheet.write(current_row, 4, d['Total'], fmt_cell)
            worksheet.write(current_row, 5, d['Saldo'], fmt_cell)
            for i, a in enumerate(areas):
                val = d[a]
                worksheet.write(current_row, 6+i, val if val > 0 else "", fmt_cell)
            worksheet.write(current_row, 6+len(areas), d['Cant'], fmt_cell)
            current_row += 1
        current_row += 2
    writer.close()
    return output

def componente_seleccion_libros(inventario, key_suffix, seleccion_previa=None, reset_counter=0):
    grados = inventario['Grado'].unique()
    seleccion = []
    total = 0
    for grado in grados:
        df_g = inventario[inventario['Grado'] == grado]
        with st.expander(f"{grado}"):
            for _, r in df_g.iterrows():
                key = f"{grado}_{r['Area']}_{r['Libro']}_{key_suffix}_{reset_counter}"
                nombre = str(r['Libro']).strip()
                area = str(r['Area']).strip()
                precio = limpiar_moneda(r['Precio Venta'])
                label = f"{area} - {nombre} (${int(precio):,})"
                item_new = f"[{grado}] ({area}) {nombre}"
                item_old = f"[{grado}] {nombre}"
                checked = False
                if seleccion_previa:
                    if item_new in seleccion_previa or item_old in seleccion_previa: checked = True
                if st.checkbox(label, key=key, value=checked):
                    seleccion.append(item_new)
                    total += precio
    return seleccion, total

def renderizar_matriz_lectura(fila, inventario):
    st.markdown(f"**Pedido:** {fila['ID_Pedido']} | **Fecha:** {fila['Fecha_Creacion']}")
    c1, c2, c3 = st.columns(3)
    tot = limpiar_moneda(fila.get('Total', 0))
    abo = limpiar_moneda(fila.get('Abonado', 0))
    sal = limpiar_moneda(fila.get('Saldo', 0))

    c1.metric("Total", f"${tot:,.0f}")
    c2.metric("Abonado", f"${abo:,.0f}")
    c3.metric("Saldo", f"${sal:,.0f}", delta_color="inverse")
    
    detalles = str(fila['Detalle'])
    items = detalles.split(" | ")
    libros_grado = {}
    for item in items:
        match = re.search(r'\[(.*?)\]', item)
        if match:
            g = match.group(1)
            if g not in libros_grado: libros_grado[g] = []
            libros_grado[g].append(item)
            
    for g, lista in libros_grado.items():
        st.caption(f"🎓 Grado: {g}")
        inv_g = inventario[inventario['Grado'] == g]
        if not inv_g.empty:
            areas = inv_g['Area'].unique()
            data = {a: ["❌"] for a in areas}
            for it in lista:
                area_enc = None
                match_a = re.search(r'\((.*?)\)', it)
                if match_a:
                    pos = match_a.group(1).strip()
                    for a in areas:
                        if str(a).strip().lower() == pos.lower():
                            area_enc = a
                            break
                if area_enc: data[area_enc] = ["✅"]
            st.table(pd.DataFrame(data))

    st.markdown("**📂 Soportes Adjuntos:**")
    cs1, cs2 = st.columns(2)
    s1 = str(fila.get('Comprobante', 'No'))
    s2 = str(fila.get('Comprobante2', 'No'))
    
    with cs1:
        if s1.startswith("http"): st.image(s1, caption="Soporte 1", use_container_width=True)
        elif s1 not in ['No', 'Manual', 'Manual/Presencial', 'nan']: st.warning("Imagen no disponible")
        else: st.info("Sin soporte inicial")
        
    with cs2:
        if s2.startswith("http"): st.image(s2, caption="Soporte 2", use_container_width=True)
        elif s2 not in ['No', 'nan']: st.warning("Imagen no disponible")
        else: st.info("-")
    st.divider()

def formulario_pedido(pedido_id):
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("⚠️ Error conectando a Google Sheets.")
        return

    nequi_num = obtener_celular_nequi()
    
    datos = {}
    es_modif = False
    
    if pedido_id:
        df = cargar_pedidos()
        row = df[df['ID_Pedido'] == str(pedido_id)]
        if not row.empty:
            datos = row.iloc[0].to_dict()
            es_modif = True
            st.info(f"📝 Editando Pedido: {datos['ID_Pedido']}")

    c1, c2 = st.columns(2)
    nom = c1.text_input("Nombre Completo", value=datos.get('Cliente', ''))
    cel = c2.text_input("Celular", value=datos.get('Celular', ''))

    st.divider()
    st.subheader("Necesito ayuda en:")
    items, total = componente_seleccion_libros(inventario, "form", datos.get('Detalle', ''))
    
    st.divider()
    cm, cb = st.columns([2,1])
    cm.metric("Total a Pagar", f"${total:,.0f}")
    if cb.button("🔄 Actualizar Precio"): pass
    
    st.subheader("Pagos y Soportes")
    
    # --- RECUADRO NEQUI COMPACTO ---
    st.markdown(f"""
    <div style="
        border: 1px solid rgba(128, 128, 128, 0.3);
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 15px;
        background-color: rgba(128, 128, 128, 0.08);
        color: inherit;
        width: fit-content;
        font-size: 0.9em;">
        <span style="font-weight: bold; margin-right: 10px;">📱 Cuenta Nequi:</span>
        <span style="font-family: monospace; font-size: 1.1em;">{nequi_num}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # --- NOTA WHATSAPP ---
    st.info("""**IMPORTANTE:**
* Realiza todos tus pagos en el Nequi que se indica arriba y envía el comprobante por WhatsApp.
* Para confirmar su pedido, se requiere de un anticipo del 50% y el saldo Contraentrega.
* Tiempo de Entrega entre 6 días hábiles, contados a partir del pago del anticipo.""")
    
    # --- BLOQUE DEUDA UNIFICADO (SOLO LECTURA) ---
    prev_abo = limpiar_moneda(datos.get('Abonado', 0))
    saldo_pend = total - prev_abo
    if es_modif:
        st.markdown(f"""
        <div style="margin-top: 10px; margin-bottom: 15px; line-height: 1.2;">
            <div><strong>Abono Previo:</strong> ${prev_abo:,.0f}</div>
            <div style="color: #d9534f;"><strong>Saldo Deuda:</strong> ${saldo_pend:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.write("---")
    if st.button("✅ CONFIRMAR Y GUARDAR"):
        with st.spinner("Guardando Pedido..."):
            acumulado = prev_abo
            
            if not nom or not cel: st.error("Faltan datos personales")
            elif total == 0: st.error("Seleccione libros")
            else:
                df_ped = cargar_pedidos()
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                saldo = total - acumulado
                
                if es_modif: curr_id = str(pedido_id)
                else: curr_id = obtener_nuevo_id(df_ped)
                
                n_f1 = datos.get('Comprobante', 'No')
                n_f2 = datos.get('Comprobante2', 'No')
                
                hist = datos.get('Historial_Cambios', 'Original')
                if es_modif: hist += f" | Modif: {fecha}"

                nuevo_registro = {
                    "ID_Pedido": curr_id, "Fecha_Creacion": fecha if not es_modif else datos['Fecha_Creacion'],
                    "Ultima_Modificacion": fecha, "Cliente": nom, "Celular": cel,
                    "Detalle": " | ".join(items), "Total": total, "Abonado": acumulado,
                    "Saldo": saldo, "Estado": datos.get('Estado', 'Nuevo'),
                    "Comprobante": n_f1, "Comprobante2": n_f2, "Historial_Cambios": hist
                }
                
                if es_modif:
                    idx = df_ped[df_ped['ID_Pedido'] == curr_id].index
                    if not idx.empty:
                        for k, v in nuevo_registro.items(): df_ped.at[idx[0], k] = v
                else:
                    df_ped = pd.concat([df_ped, pd.DataFrame([nuevo_registro])], ignore_index=True)
                
                guardar_pedido_db(df_ped)
                st.session_state.exito_cliente = True
                st.session_state.ultimo_pedido_cliente = curr_id
                st.rerun()

def vista_cliente(pid_param=None):
    if pid_param:
        formulario_pedido(pid_param)
        return

    st.image("https://cdn-icons-png.flaticon.com/512/2232/2232688.png", width=60)
    st.title("📚 Pedido de Ayuda Escolar")
    
    op = st.radio("Menú:", ["• Crear Pedidos", "• Revisar Pedido", "• Editar Pedidos / Confirmar un Pago"], horizontal=True)
    st.divider()
    
    if op == "• Crear Pedidos":
        formulario_pedido(None)
        
    elif op == "• Revisar Pedido":
        st.subheader("🔍 Consultar")
        b = st.text_input("Tu celular registrado:")
        if st.button("Buscar"):
            if b:
                df = cargar_pedidos()
                inv = cargar_inventario()
                clean = limpiar_numero(b)
                df['cc'] = df['Celular'].apply(limpiar_numero)
                res = df[df['cc'] == clean]
                if res.empty: st.error("No encontrado")
                else:
                    res['Saldo_Num'] = res['Saldo'].apply(limpiar_moneda)
                    pends = res[res['Saldo_Num'] > 0]
                    if not pends.empty:
                        st.info(f"Tienes {len(pends)} pedidos pendientes:")
                        for _, r in pends.iterrows(): renderizar_matriz_lectura(r, inv)
                    else:
                        st.success("Estás al día. Último pedido:")
                        renderizar_matriz_lectura(res.iloc[-1], inv)
                        
    elif op == "• Editar Pedidos / Confirmar un Pago":
        st.subheader("💳 Pagar / Editar")
        b = st.text_input("Tu celular:")
        if st.button("Buscar Pendientes"): st.session_state.edit_found = False
        
        if b:
            df = cargar_pedidos()
            clean = limpiar_numero(b)
            df['cc'] = df['Celular'].apply(limpiar_numero)
            df['Saldo_Num'] = df['Saldo'].apply(limpiar_moneda)
            pends = df[(df['cc'] == clean) & (df['Saldo_Num'] > 0)]
            
            if pends.empty: st.info("No tienes deudas pendientes.")
            else:
                opts = {f"{r['ID_Pedido']} - {r['Fecha_Creacion']} ($ Deuda: {r['Saldo']})": r['ID_Pedido'] for _, r in pends.iterrows()}
                sel = st.selectbox("Selecciona pedido:", list(opts.keys()))
                if sel:
                    st.divider()
                    formulario_pedido(opts[sel])

def vista_exito(pid):
    st.balloons()
    st.success("¡Pedido Guardado en la Nube Exitosamente!")
    
    df = cargar_pedidos()
    if not df.empty and 'ID_Pedido' in df.columns:
        row = df[df['ID_Pedido'] == str(pid)]
        if not row.empty: 
            inv = cargar_inventario()
            renderizar_matriz_lectura(row.iloc[0], inv)
    st.divider()
    if st.button("⬅️ Inicio"):
        st.session_state.exito_cliente = False
        st.rerun()

def vista_admin():
    url_app = "https://app-libros-escolares-kayrovn4lncquvsdmusqd8.streamlit.app/"
    menu = st.sidebar.radio("Ir a:", ["📊 Ventas", "📦 Inventario", "⚙️ Configuración"])
    
    if menu == "⚙️ Configuración":
        st.title("⚙️ Configuración del Sistema")
        st.info("Aquí puedes cambiar el número de Nequi que ven todos los clientes.")
        actual = obtener_celular_nequi()
        nuevo = st.text_input("Número Nequi Actual:", value=actual)
        if st.button("💾 Guardar Configuración"):
            if guardar_celular_nequi(nuevo):
                st.success("¡Número actualizado exitosamente!")
                st.rerun()
            else: st.error("Error guardando en Google Sheets.")
    
    elif menu == "📦 Inventario":
        st.title("📦 Inventario en Nube (Google Sheets)")
        st.info("ℹ️ Para agregar o modificar libros, edita directamente tu archivo 'DB_Libros_Escolares' en Google Drive.")
        df = cargar_inventario()
        if not df.empty:
            df_ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            if st.button("💾 Guardar Cambios Rápidos"):
                guardar_inventario(df_ed)
                st.success("¡Inventario actualizado!")
                st.rerun()
            st.divider()
            try:
                df['Ganancia'] = df['Precio Venta'] - df['Costo']
                res = df.groupby("Grado")[["Costo", "Precio Venta", "Ganancia"]].sum()
                st.dataframe(res, use_container_width=True)
            except: pass
        else: st.warning("Inventario vacío.")

    elif menu == "📊 Ventas":
        st.title("📊 Panel Ventas (Google Sheets)")
        df = cargar_pedidos()
        
        c1, c2 = st.columns(2)
        with c1:
            tel = st.text_input("WhatsApp Cliente:")
            if tel: st.link_button("Enviar Link", generar_link_whatsapp(tel, f"Hola, pide aquí: {url_app}?rol=cliente"))
        with c2: st.code(f"{url_app}?rol=cliente", language="text")
            
        st.divider()
        with st.expander("➕ Pedido Manual"):
            st.caption("Usa esto si un padre está contigo en persona.")
            inv = cargar_inventario()
            if not inv.empty:
                mn, mc = st.columns(2)
                nom = mn.text_input("Cliente", key="mn")
                cel = mc.text_input("Cel", key="mc")
                its, tot = componente_seleccion_libros(inv, "man", reset_counter=st.session_state.reset_manual)
                st.metric("Total", f"${tot:,.0f}")
                abo = st.number_input("Abono:", step=1000.0)
                est = st.selectbox("Estado:", ["Nuevo", "Pagado Total", "Entregado"])
                
                if st.button("Guardar Manual"):
                    if not nom: st.error("Nombre?")
                    else:
                        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        nid = obtener_nuevo_id(df)
                        nuevo = {
                            "ID_Pedido": nid, "Fecha_Creacion": fecha, "Ultima_Modificacion": fecha,
                            "Cliente": nom, "Celular": cel, "Detalle": " | ".join(its),
                            "Total": tot, "Abonado": abo, "Saldo": tot - abo, "Estado": est,
                            "Comprobante": "Manual", "Comprobante2": "No", "Historial_Cambios": "Admin Manual"
                        }
                        df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
                        guardar_pedido_db(df)
                        st.success(f"Guardado ID: {nid}")
                        st.session_state.reset_manual += 1
                        st.rerun()

        st.divider()
        st.subheader("Listado de Pedidos")
        inv_act = cargar_inventario()
        if not df.empty and not inv_act.empty:
            excel = generar_excel_matriz_bytes(df, inv_act)
            st.download_button("📥 Descargar Reporte", excel, "Reporte_Matriz.xlsx")
            
        filtro = st.text_input("Buscar Pedido:")
        df_view = df
        if filtro: df_view = df[df['Cliente'].str.contains(filtro, case=False, na=False)]
        
        vista_modo = st.radio("Modo de Visualización:", ["Vista Lista (Edición Rápida)", "Vista Matriz (Detallada)"], horizontal=True)
        
        if vista_modo == "Vista Lista (Edición Rápida)":
            cols_base = ["ID_Pedido", "Fecha_Creacion", "Ultima_Modificacion", "Cliente", "Estado", "Total", "Abonado", "Saldo", "Celular"]
            cols_extra = [c for c in df_view.columns if c not in cols_base]
            df_view = df_view[cols_base + cols_extra]
            
            def resaltar_modificaciones(row):
                estilo = [''] * len(row)
                try:
                    if row['Ultima_Modificacion'] > row['Fecha_Creacion']:
                        idx = row.index.get_loc('Ultima_Modificacion')
                        estilo[idx] = 'color: #d9534f; font-weight: bold;'
                except: pass
                return estilo

            st.caption("💡 Fechas en rojo indican modificaciones posteriores. **Nota:** Puedes editar el 'Estado', 'Abonado' y 'Saldo' en la tabla de abajo.")
            st.dataframe(df_view.style.apply(resaltar_modificaciones, axis=1), use_container_width=True)
            
            st.markdown("**Editar Registros Financieros y de Estado:**")
            edited = st.data_editor(
                df_view[["ID_Pedido", "Cliente", "Estado", "Abonado", "Saldo"]],
                column_config={
                    "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"]),
                    "ID_Pedido": st.column_config.TextColumn(disabled=True),
                    "Cliente": st.column_config.TextColumn(disabled=True),
                },
                hide_index=True, use_container_width=True, key="editor_rapido"
            )
            
            if st.button("💾 Guardar Cambios"):
                cambios = False
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for idx, row in edited.iterrows():
                    mask = df['ID_Pedido'] == row['ID_Pedido']
                    if mask.any():
                        fila_original = df.loc[mask].iloc[0]
                        hubo_cambio_fila = False
                        
                        if fila_original['Estado'] != row['Estado']:
                            df.loc[mask, 'Estado'] = row['Estado']
                            hubo_cambio_fila = True
                            
                        abo_original = limpiar_moneda(fila_original['Abonado'])
                        abo_nuevo = limpiar_moneda(row['Abonado'])
                        if abo_original != abo_nuevo:
                            df.loc[mask, 'Abonado'] = row['Abonado']
                            hubo_cambio_fila = True
                            
                        saldo_original = limpiar_moneda(fila_original['Saldo'])
                        saldo_nuevo = limpiar_moneda(row['Saldo'])
                        if saldo_original != saldo_nuevo:
                             df.loc[mask, 'Saldo'] = row['Saldo']
                             hubo_cambio_fila = True
                             
                        if hubo_cambio_fila:
                            df.loc[mask, 'Ultima_Modificacion'] = fecha_actual
                            cambios = True

                if cambios:
                    guardar_pedido_db(df)
                    st.success("¡Registros guardados con éxito!")
                    st.rerun()
                else: st.info("No detecté cambios.")
        
        else:
            st.info("ℹ️ Visualización de items comprados por grado.")
            if not inv_act.empty:
                grados_disp = inv_act['Grado'].unique()
                grado_sel = st.selectbox("Selecciona Grado:", grados_disp)
                if grado_sel:
                    inv_g = inv_act[inv_act['Grado'] == grado_sel]
                    areas = inv_g['Area'].unique()
                    patron = f"[{grado_sel}]"
                    df_grado = df_view[df_view['Detalle'].str.contains(patron, regex=False, na=False)].copy()
                    if not df_grado.empty:
                        for a in areas: df_grado[a] = False
                        for idx, row in df_grado.iterrows():
                            items = str(row['Detalle']).split(" | ")
                            for item in items:
                                if patron in item:
                                    match = re.search(r'\((.*?)\)', item)
                                    if match:
                                        pos = match.group(1).strip()
                                        for a in areas:
                                            if str(a).strip().lower() == pos.lower():
                                                df_grado.at[idx, a] = True
                        
                        cols_ver = ["ID_Pedido", "Fecha_Creacion", "Ultima_Modificacion", "Cliente", "Estado"] + list(areas)
                        st.dataframe(df_grado[cols_ver], hide_index=True, use_container_width=True)
                    else: st.warning(f"No hay pedidos para {grado_sel}")

        st.divider()
        st.subheader("Gestión Detallada")
        opts = df['ID_Pedido'] + " - " + df['Cliente']
        bf = st.text_input("Filtrar Gestión:", placeholder="ID o Nombre...")
        if bf: opts = opts[opts.str.contains(bf, case=False, na=False)]
        
        lista_clientes = ["-Selección del cliente-"] + list(opts)
        sel_g = st.selectbox("Seleccionar:", lista_clientes)
        
        if sel_g and sel_g != "-Selección del cliente-":
            id_sel = sel_g.split(" - ")[0]
            row_sel = df[df['ID_Pedido'] == id_sel].iloc[0]
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("Soporte 1")
                s1 = str(row_sel.get('Comprobante', 'No'))
                if s1.startswith("http"): st.image(s1, caption="Soporte 1", use_container_width=True)
                else: st.info("Sin imagen Online")
            with c2:
                st.caption("Soporte 2")
                s2 = str(row_sel.get('Comprobante2', 'No'))
                if s2.startswith("http"): st.image(s2, caption="Soporte 2", use_container_width=True)
                else: st.info("-")
            with c3:
                if st.button("🗑️ ELIMINAR PEDIDO", type="primary"):
                    df = df[df['ID_Pedido'] != id_sel]
                    guardar_pedido_db(df)
                    st.success("Eliminado")
                    st.rerun()

qp = st.query_params
rol = qp.get("rol")
if rol == "cliente":
    if st.session_state.exito_cliente and st.session_state.ultimo_pedido_cliente:
        vista_exito(st.session_state.ultimo_pedido_cliente)
    else: vista_cliente(qp.get("pedido_id"))
else:
    if not st.session_state.admin_autenticado:
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, c, _ = st.columns([1,2,1])
        with c:
            st.title("🔒 Admin")
            pwd = st.text_input("Contraseña:", type="password")
            if st.button("Entrar"):
                if pwd == st.secrets.get("PASSWORD_ADMIN", "12345"):
                    st.session_state.admin_autenticado = True
                    st.rerun()
                else: st.error("Incorrecto")
    else:
        vista_admin()