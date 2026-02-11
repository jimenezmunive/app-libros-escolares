import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import json
import os
import io
import unicodedata
import re
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Pedido de Ayuda Escolar", layout="wide", page_icon="📚")

# --- CONFIGURACIÓN GOOGLE ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SHEET_NAME = "DB_Libros_Escolares"

# --- ESTADO ---
if 'reset_manual' not in st.session_state: st.session_state.reset_manual = 0
if 'exito_cliente' not in st.session_state: st.session_state.exito_cliente = False
if 'ultimo_pedido_cliente' not in st.session_state: st.session_state.ultimo_pedido_cliente = None
if 'admin_autenticado' not in st.session_state: st.session_state.admin_autenticado = False

# --- CONEXIÓN ROBUSTA (SHEETS + DRIVE) ---
@st.cache_resource
def obtener_credenciales():
    try:
        json_str = st.secrets["google_json"]
        creds_dict = json.loads(json_str)
        return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except Exception as e:
        st.error(f"Error Credenciales: {e}")
        return None

def conectar_sheets():
    creds = obtener_credenciales()
    if creds:
        client = gspread.authorize(creds)
        return client
    return None

def conectar_drive():
    creds = obtener_credenciales()
    if creds:
        service = build('drive', 'v3', credentials=creds)
        return service
    return None

# --- FUNCIÓN: SUBIR IMAGEN A GOOGLE DRIVE (PERSISTENTE) ---
def subir_imagen_drive(uploaded_file, nombre_archivo):
    """Sube la imagen a Drive y devuelve un Link público para verla"""
    if uploaded_file is None: return "No"
    
    try:
        service = conectar_drive()
        if not service: return "Error Conexión Drive"
        
        # 1. Crear metadata del archivo
        file_metadata = {'name': nombre_archivo}
        
        # 2. Preparar el contenido (Bytes)
        media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)
        
        # 3. Subir archivo
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webContentLink'
        ).execute()
        
        file_id = file.get('id')
        
        # 4. Hacer el archivo "Público" (Reader) para que la App pueda mostrarlo
        # (Esto es necesario para que st.image pueda leer la URL)
        permission = {'type': 'anyone', 'role': 'reader'}
        service.permissions().create(fileId=file_id, body=permission).execute()
        
        # 5. Retornar el link directo de descarga/visualización
        return file.get('webContentLink')
        
    except Exception as e:
        st.error(f"Error subiendo a Drive: {e}")
        return "Error"

# --- FUNCIONES DE LIMPIEZA ---
def limpiar_moneda(valor):
    try:
        if isinstance(valor, (int, float)): return float(valor)
        valor_str = str(valor).strip()
        if not valor_str: return 0.0
        valor_str = valor_str.replace('$', '').replace(' ', '').replace(',', '')
        return float(valor_str)
    except: return 0.0

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
        sh = client.open(SHEET_NAME)
        wk = sh.worksheet("Inventario")
        data = wk.get_all_records()
        if not data: return pd.DataFrame(columns=["Grado", "Area", "Libro", "Costo", "Precio Venta"])
        df = pd.DataFrame(data)
        
        cols_texto = ['Grado', 'Area', 'Libro']
        for col in cols_texto:
            if col in df.columns: df[col] = df[col].astype(str).str.strip()
            
        if 'Precio Venta' in df.columns: df['Precio Venta'] = df['Precio Venta'].apply(limpiar_moneda)
        else: df['Precio Venta'] = 0.0
        
        if 'Costo' in df.columns: df['Costo'] = df['Costo'].apply(limpiar_moneda)
        else: df['Costo'] = 0.0
        
        return df
    except Exception as e:
        st.error(f"Error Inventario: {e}")
        return pd.DataFrame()

def guardar_inventario(df):
    client = conectar_sheets()
    if not client: return
    try:
        sh = client.open(SHEET_NAME)
        wk = sh.worksheet("Inventario")
        df['Costo'] = df['Costo'].apply(limpiar_moneda)
        df['Precio Venta'] = df['Precio Venta'].apply(limpiar_moneda)
        df['Ganancia'] = df['Precio Venta'] - df['Costo']
        wk.clear()
        wk.update([df.columns.values.tolist()] + df.values.tolist())
        st.cache_data.clear()
    except Exception as e: st.error(f"Error guardando: {e}")

def cargar_pedidos():
    client = conectar_sheets()
    if not client: return pd.DataFrame()
    try:
        sh = client.open(SHEET_NAME)
        wk = sh.worksheet("Pedidos")
        data = wk.get_all_records()
        if not data: return pd.DataFrame(columns=["ID_Pedido", "Cliente", "Celular", "Total", "Abonado", "Saldo", "Estado", "Comprobante", "Comprobante2"])
        df = pd.DataFrame(data)
        if 'ID_Pedido' in df.columns: df['ID_Pedido'] = df['ID_Pedido'].astype(str)
        if "Comprobante2" not in df.columns: df["Comprobante2"] = "No"
        return df
    except: return pd.DataFrame()

def guardar_pedido_db(df):
    client = conectar_sheets()
    if not client: return
    try:
        sh = client.open(SHEET_NAME)
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
        
        mapa_legacy = {normalizar_clave(k): v for k, v in zip(inv_grado['Libro'], inv_grado['Area'])}
        areas = inv_grado['Area'].unique()
        patron = f"[{grado}]"
        
        pedidos_grado = df_pedidos[df_pedidos['Detalle'].str.contains(patron, regex=False, na=False)].copy()
        if pedidos_grado.empty: continue

        data_rows = []
        for _, p in pedidos_grado.iterrows():
            row = {'Cliente': p['Cliente'], 'Celular': p['Celular'], 'Total': p['Total'], 'Saldo': p['Saldo']}
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
                        area_enc = mapa_legacy.get(normalizar_clave(raw))
                    if area_enc:
                        row[area_enc] = 1
                        count += 1
            row['Cant'] = count
            data_rows.append(row)

        if not data_rows: continue
        
        worksheet.write(current_row, 0, f"GRADO: {grado}", fmt_header)
        current_row += 1
        headers = ['Cliente', 'Celular', 'Total', 'Saldo'] + list(areas) + ['Cant']
        for i, h in enumerate(headers): worksheet.write(current_row, i, h, fmt_col)
        current_row += 1
        
        for d in data_rows:
            worksheet.write(current_row, 0, d['Cliente'], fmt_cell)
            worksheet.write(current_row, 1, d['Celular'], fmt_cell)
            worksheet.write(current_row, 2, d['Total'], fmt_cell)
            worksheet.write(current_row, 3, d['Saldo'], fmt_cell)
            for i, a in enumerate(areas):
                val = d[a]
                worksheet.write(current_row, 4+i, val if val > 0 else "", fmt_cell)
            worksheet.write(current_row, 4+len(areas), d['Cant'], fmt_cell)
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
                precio = r['Precio Venta']
                
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
        if s1.startswith("http"):
            st.image(s1, width=200, caption="Soporte 1 (Drive)")
        elif s1 not in ['No', 'Manual', 'Manual/Presencial', 'nan']:
            st.warning("Imagen local expiró. Subir de nuevo.")
        else: st.info("Sin soporte inicial")
        
    with cs2:
        if s2.startswith("http"):
            st.image(s2, width=200, caption="Soporte 2 (Drive)")
        elif s2 not in ['No', 'nan']:
            st.warning("Imagen local expiró.")
        else: st.info("-")
    st.divider()

def formulario_pedido(pedido_id):
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("⚠️ Error conectando a Google Sheets.")
        return

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
    tipo = st.radio("Método:", ["Pago Total", "Abono Parcial"], horizontal=True)
    
    prev_abo = limpiar_moneda(datos.get('Abonado', 0))
    if es_modif: st.write(f"**Abonado Previo:** ${prev_abo:,.0f}")
    
    new_abo = st.number_input("Valor a transferir HOY:", min_value=0.0, step=1000.0)
    st.caption("ℹ️ Nota: El valor será validado administrativamente.")
    
    f1, f2 = None, None
    if es_modif:
        st.markdown("**📂 Soporte 1 (Solo Lectura):**")
        s1 = str(datos.get('Comprobante', 'No'))
        if s1.startswith("http"): st.image(s1, width=200)
        elif s1 not in ['No', 'Manual/Presencial']: st.warning("Imagen antigua expirada")
        else: st.info("No hay soporte inicial")
        
        st.markdown("**📂 Cargar Soporte 2 (Si abona hoy):**")
        f2 = st.file_uploader("Subir 2do Comprobante", type=['jpg','png','jpeg','pdf'])
    else:
        st.markdown("**📂 Cargar Soporte de Pago:**")
        f1 = st.file_uploader("Subir Comprobante", type=['jpg','png','jpeg','pdf'])
    
    st.write("---")
    if st.button("✅ CONFIRMAR Y GUARDAR"):
        with st.spinner("Subiendo a Google Drive y Guardando..."):
            acumulado = prev_abo + new_abo
            
            if not nom or not cel: st.error("Faltan datos personales")
            elif total == 0: st.error("Seleccione libros")
            elif (not es_modif) and (new_abo == 0): st.error("Ingrese abono")
            elif (not es_modif) and (not f1): st.error("Falta comprobante")
            elif tipo == "Pago Total" and acumulado < total:
                st.error(f"Pago Total requiere ${total:,.0f}. Llevas ${acumulado:,.0f}")
            else:
                df_ped = cargar_pedidos()
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                saldo = total - acumulado
                
                if es_modif: curr_id = str(pedido_id)
                else: curr_id = obtener_nuevo_id(df_ped)
                
                # --- SUBIDA A DRIVE ---
                n_f1 = datos.get('Comprobante', 'No')
                n_f2 = datos.get('Comprobante2', 'No')
                
                if f1:
                    link1 = subir_imagen_drive(f1, f"PED-{curr_id}-SOP1")
                    if link1 != "Error": n_f1 = link1
                    else: st.error("Falló la subida a Drive (Soporte 1)")

                if f2:
                    link2 = subir_imagen_drive(f2, f"PED-{curr_id}-SOP2")
                    if link2 != "Error": n_f2 = link2
                    else: st.error("Falló la subida a Drive (Soporte 2)")
                
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
    inv = cargar_inventario()
    row = df[df['ID_Pedido'] == str(pid)]
    if not row.empty: renderizar_matriz_lectura(row.iloc[0], inv)
    st.divider()
    if st.button("⬅️ Inicio"):
        st.session_state.exito_cliente = False
        st.rerun()

def vista_admin():
    url_app = "https://app-libros-escolares-kayrovn4lncquvsdmusqd8.streamlit.app/"
    menu = st.sidebar.radio("Ir a:", ["📊 Ventas", "📦 Inventario"])
    
    if menu == "📦 Inventario":
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
        st.subheader("Listado")
        inv_act = cargar_inventario()
        if not df.empty and not inv_act.empty:
            excel = generar_excel_matriz_bytes(df, inv_act)
            st.download_button("📥 Descargar Reporte", excel, "Reporte_Matriz.xlsx")
            
        filtro = st.text_input("Buscar Pedido:")
        df_view = df
        if filtro: df_view = df[df['Cliente'].str.contains(filtro, case=False, na=False)]
        
        edited = st.data_editor(
            df_view,
            column_config={
                "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"]),
                "ID_Pedido": st.column_config.TextColumn(disabled=True),
                "Detalle": st.column_config.TextColumn(disabled=True),
                "Total": st.column_config.NumberColumn(format="$%d"),
                "Saldo": st.column_config.NumberColumn(format="$%d")
            },
            hide_index=True, use_container_width=True
        )
        if st.button("💾 Guardar Cambios Estados"):
            cambios = False
            for idx, row in edited.iterrows():
                mask = df['ID_Pedido'] == row['ID_Pedido']
                if mask.any():
                    if df.loc[mask, 'Estado'].values[0] != row['Estado']:
                        df.loc[mask, 'Estado'] = row['Estado']
                        cambios = True
                    saldo_original = limpiar_moneda(df.loc[mask, 'Saldo'].values[0])
                    saldo_nuevo = limpiar_moneda(row['Saldo'])
                    if saldo_original != saldo_nuevo:
                         df.loc[mask, 'Saldo'] = row['Saldo']
                         cambios = True
            if cambios:
                guardar_pedido_db(df)
                st.success("Guardado")
            else: st.info("Sin cambios")
            
        st.divider()
        st.subheader("Gestión Detallada")
        opts = df['ID_Pedido'] + " - " + df['Cliente']
        bf = st.text_input("Filtrar:", placeholder="ID o Nombre...")
        if bf: opts = opts[opts.str.contains(bf, case=False, na=False)]
        
        sel_g = st.selectbox("Seleccionar:", opts)
        if sel_g:
            id_sel = sel_g.split(" - ")[0]
            row_sel = df[df['ID_Pedido'] == id_sel].iloc[0]
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("Soporte 1")
                s1 = str(row_sel.get('Comprobante', 'No'))
                if s1.startswith("http"): st.image(s1, width=200, caption="Drive")
                else: st.info("Sin imagen online")
            with c2:
                st.caption("Soporte 2")
                s2 = str(row_sel.get('Comprobante2', 'No'))
                if s2.startswith("http"): st.image(s2, width=200, caption="Drive")
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
        if st.sidebar.button("Salir"):
            st.session_state.admin_autenticado = False
            st.rerun()
        vista_admin()