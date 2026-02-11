import streamlit as st
import pandas as pd
import os
import io
import shutil
import unicodedata
import re
from datetime import datetime
import uuid

st.set_page_config(page_title="Pedido de Ayuda Escolar", layout="wide", page_icon="📚")

# --- CONFIGURACIÓN DE RUTAS ---
FILE_INVENTARIO = 'inventario.csv'
FILE_PEDIDOS = 'base_datos_pedidos.csv'
DIR_COMPROBANTES = 'comprobantes'

if not os.path.exists(DIR_COMPROBANTES):
    os.makedirs(DIR_COMPROBANTES)

# --- INICIALIZAR ESTADO DE SESIÓN ---
if 'reset_manual' not in st.session_state:
    st.session_state.reset_manual = 0
if 'exito_cliente' not in st.session_state:
    st.session_state.exito_cliente = False
if 'ultimo_pedido_cliente' not in st.session_state:
    st.session_state.ultimo_pedido_cliente = None

# --- FUNCIONES AUXILIARES ---
def normalizar_clave(texto):
    """Normaliza texto para búsquedas"""
    if not isinstance(texto, str): texto = str(texto)
    texto = texto.strip().lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return texto

def limpiar_numero(num):
    """Deja solo números para comparar celulares"""
    return re.sub(r'\D', '', str(num))

def obtener_nuevo_id(df_pedidos):
    """Genera un ID consecutivo (0001, 0002...)."""
    max_id = 0
    if not df_pedidos.empty:
        for pid in df_pedidos['ID_Pedido']:
            if str(pid).isdigit():
                val = int(pid)
                if val > max_id:
                    max_id = val
    nuevo = max_id + 1
    return f"{nuevo:04d}"

# --- FUNCIONES DE CARGA Y GUARDADO ---
@st.cache_data
def cargar_inventario():
    if os.path.exists(FILE_INVENTARIO):
        df = pd.read_csv(FILE_INVENTARIO)
        cols_texto = ['Grado', 'Area', 'Libro']
        for col in cols_texto:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        return df
    else:
        return pd.DataFrame(columns=["Grado", "Area", "Libro", "Costo", "Precio Venta", "Ganancia"])

def guardar_inventario(df):
    cols_texto = ['Grado', 'Area', 'Libro']
    for col in cols_texto:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    for col in ['Costo', 'Precio Venta']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Ganancia'] = df['Precio Venta'] - df['Costo']
    df.to_csv(FILE_INVENTARIO, index=False)
    cargar_inventario.clear()

def cargar_pedidos():
    if os.path.exists(FILE_PEDIDOS):
        df = pd.read_csv(FILE_PEDIDOS)
        df['ID_Pedido'] = df['ID_Pedido'].astype(str)
        if "Comprobante2" not in df.columns:
            df["Comprobante2"] = "No"
        return df
    else:
        return pd.DataFrame(columns=[
            "ID_Pedido", "Fecha_Creacion", "Ultima_Modificacion", "Cliente", "Celular", 
            "Detalle", "Total", "Abonado", "Saldo", "Estado", "Comprobante", "Comprobante2", "Historial_Cambios"
        ])

def guardar_pedido_db(df):
    df.to_csv(FILE_PEDIDOS, index=False)

def guardar_archivo_soporte(uploaded_file, id_pedido, sufijo=""):
    if uploaded_file is None:
        return "No"
    try:
        file_ext = uploaded_file.name.split('.')[-1]
        nombre_final = f"{id_pedido}{sufijo}.{file_ext}"
        ruta_completa = os.path.join(DIR_COMPROBANTES, nombre_final)
        with open(ruta_completa, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return nombre_final
    except Exception as e:
        st.error(f"Error guardando imagen: {e}")
        return "Error"

def generar_link_whatsapp(celular, mensaje):
    celular = str(celular).replace(" ", "").replace("+", "").strip()
    if not celular.startswith("57"): 
        celular = "57" + celular
    texto_codificado = mensaje.replace(" ", "%20").replace("\n", "%0A")
    return f"https://wa.me/{celular}?text={texto_codificado}"

# --- GENERADOR EXCEL MATRIZ ---
def generar_excel_matriz_bytes(df_pedidos, df_inventario):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    worksheet = workbook.add_worksheet("Listado Matriz")
    
    fmt_header_grado = workbook.add_format({'bold': True, 'font_size': 14, 'bg_color': '#DDEBF7', 'border': 1})
    fmt_col_header = workbook.add_format({'bold': True, 'bg_color': '#FFF2CC', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    fmt_cell = workbook.add_format({'border': 1, 'align': 'center'})
    fmt_cell_text = workbook.add_format({'border': 1, 'align': 'left'})
    fmt_money = workbook.add_format({'border': 1, 'num_format': '$#,##0', 'align': 'right'})
    fmt_total_row = workbook.add_format({'bold': True, 'bg_color': '#E2EFDA', 'border': 1, 'align': 'center'})

    current_row = 0
    grados_ordenados = df_inventario['Grado'].unique()

    for grado in grados_ordenados:
        inv_grado = df_inventario[df_inventario['Grado'] == grado]
        if inv_grado.empty: continue
        
        mapa_libro_area_legacy = {normalizar_clave(k): v for k, v in zip(inv_grado['Libro'], inv_grado['Area'])}
        areas_unicas = inv_grado['Area'].unique()
        patron_grado = f"[{grado}]"
        
        pedidos_grado = df_pedidos[df_pedidos['Detalle'].str.contains(patron_grado, regex=False, na=False)].copy()
        
        if pedidos_grado.empty: continue

        data_rows = []
        for idx, pedido in pedidos_grado.iterrows():
            row_dict = {
                'Cliente': pedido['Cliente'],
                'Celular': pedido['Celular'],
                'Total Pedido': pedido['Total'],
                'Saldo': pedido['Saldo']
            }
            for area in areas_unicas: row_dict[area] = 0
            
            items = str(pedido['Detalle']).split(" | ")
            libros_comprados_count = 0
            
            for item in items:
                if patron_grado in item:
                    area_encontrada = None
                    match = re.search(r'\((.*?)\)', item)
                    if match:
                        posible_area = match.group(1).strip()
                        for a in areas_unicas:
                            if str(a).strip().lower() == posible_area.lower():
                                area_encontrada = a
                                break
                    
                    if not area_encontrada:
                        nombre_raw = item.replace(patron_grado, "").strip()
                        key_clean = normalizar_clave(nombre_raw)
                        area_encontrada = mapa_libro_area_legacy.get(key_clean)
                    
                    if area_encontrada:
                        row_dict[area_encontrada] = 1
                        libros_comprados_count += 1
            
            row_dict['Total Libros'] = libros_comprados_count
            data_rows.append(row_dict)

        if not data_rows: continue

        worksheet.merge_range(current_row, 0, current_row, 4 + len(areas_unicas), f"GRADO: {grado}", fmt_header_grado)
        current_row += 1
        
        headers = ['Cliente', 'Celular', 'Total Pedido', 'Saldo'] + list(areas_unicas) + ['Total Libros']
        for col_num, header in enumerate(headers):
            worksheet.write(current_row, col_num, header, fmt_col_header)
            if header == 'Cliente': worksheet.set_column(col_num, col_num, 30)
            elif header == 'Celular': worksheet.set_column(col_num, col_num, 15)
            elif header in ['Total Pedido', 'Saldo']: worksheet.set_column(col_num, col_num, 15)
            else: worksheet.set_column(col_num, col_num, 12)
        current_row += 1
        
        totales_verticales = {area: 0 for area in areas_unicas}
        totales_verticales['Total Libros'] = 0

        for row_data in data_rows:
            worksheet.write(current_row, 0, row_data['Cliente'], fmt_cell_text)
            worksheet.write(current_row, 1, row_data['Celular'], fmt_cell)
            worksheet.write(current_row, 2, row_data['Total Pedido'], fmt_money)
            worksheet.write(current_row, 3, row_data['Saldo'], fmt_money)
            
            col_idx = 4
            for area in areas_unicas:
                val = row_data[area]
                worksheet.write(current_row, col_idx, val if val > 0 else "", fmt_cell)
                totales_verticales[area] += val
                col_idx += 1
            
            worksheet.write(current_row, col_idx, row_data['Total Libros'], fmt_cell)
            totales_verticales['Total Libros'] += row_data['Total Libros']
            current_row += 1
            
        worksheet.write(current_row, 0, "TOTALES GRADO", fmt_total_row)
        worksheet.write(current_row, 1, "", fmt_total_row)
        worksheet.write(current_row, 2, "", fmt_total_row)
        worksheet.write(current_row, 3, "", fmt_total_row)
        col_idx = 4
        for area in areas_unicas:
            worksheet.write(current_row, col_idx, totales_verticales[area], fmt_total_row)
            col_idx += 1
        worksheet.write(current_row, col_idx, totales_verticales['Total Libros'], fmt_total_row)
        
        current_row += 3 

    writer.close()
    return output

# --- COMPONENTE DE SELECCIÓN DE LIBROS ---
def componente_seleccion_libros(inventario, key_suffix, seleccion_previa=None, reset_counter=0):
    grados = inventario['Grado'].unique()
    seleccion_final = []
    total_final = 0
    
    for grado in grados:
        df_grado = inventario[inventario['Grado'] == grado]
        
        with st.expander(f"{grado}"):
            for index, row in df_grado.iterrows():
                key_check = f"{grado}_{row['Area']}_{row['Libro']}_{key_suffix}_{reset_counter}"
                
                nombre_libro = str(row['Libro']).strip()
                area_libro = str(row['Area']).strip()
                label = f"{area_libro} - {nombre_libro} (${int(row['Precio Venta']):,})"
                
                # FORMATO NUEVO CON ÁREA GUARDADA
                item_guardado = f"[{grado}] ({area_libro}) {nombre_libro}"
                item_viejo = f"[{grado}] {nombre_libro}"
                
                checked = False
                if seleccion_previa:
                    if item_guardado in seleccion_previa or item_viejo in seleccion_previa:
                        checked = True
                
                if st.checkbox(label, key=key_check, value=checked):
                    seleccion_final.append(item_guardado)
                    total_final += row['Precio Venta']
            
    return seleccion_final, total_final

# --- COMPONENTE DE VISUALIZACIÓN DE MATRIZ (SOLO LECTURA) ---
def renderizar_matriz_lectura(fila, inventario):
    st.markdown(f"**Pedido ID:** {fila['ID_Pedido']} | **Fecha:** {fila['Fecha_Creacion']}")
    
    col_fin1, col_fin2, col_fin3 = st.columns(3)
    col_fin1.metric("Total", f"${fila['Total']:,.0f}")
    col_fin2.metric("Abonado", f"${fila['Abonado']:,.0f}")
    col_fin3.metric("Saldo Pendiente", f"${fila['Saldo']:,.0f}", delta_color="inverse")
    
    detalles = fila['Detalle']
    items = detalles.split(" | ")
    
    libros_por_grado = {}
    for item in items:
        match_grado = re.search(r'\[(.*?)\]', item)
        if match_grado:
            g = match_grado.group(1)
            if g not in libros_por_grado: libros_por_grado[g] = []
            libros_por_grado[g].append(item)
    
    if libros_por_grado:
        for grado, lista_items in libros_por_grado.items():
            st.caption(f"🎓 Grado: {grado}")
            inv_grado = inventario[inventario['Grado'] == grado]
            
            if not inv_grado.empty:
                areas = inv_grado['Area'].unique()
                data_matrix = {area: ["❌"] for area in areas}
                
                for item in lista_items:
                    area_encontrada = None
                    match_area = re.search(r'\((.*?)\)', item)
                    if match_area:
                        posible_area = match_area.group(1).strip()
                        for a in areas:
                            if str(a).strip().lower() == posible_area.lower():
                                area_encontrada = a
                                break
                    
                    if not area_encontrada:
                        patron = f"[{grado}]"
                        nombre_raw = item.replace(patron, "").strip()
                    
                    if area_encontrada:
                        data_matrix[area_encontrada] = ["✅"]
                
                st.table(pd.DataFrame(data_matrix))
    
    # Visualizar Soportes
    st.markdown("**📂 Soportes Adjuntos:**")
    cs1, cs2 = st.columns(2)
    with cs1:
        s1 = fila.get('Comprobante', 'No')
        if s1 and s1 not in ['No', 'Manual/Presencial']:
            ruta1 = os.path.join(DIR_COMPROBANTES, s1)
            if os.path.exists(ruta1): st.image(ruta1, caption="Soporte 1", width=150)
    with cs2:
        s2 = fila.get('Comprobante2', 'No')
        if s2 and s2 not in ['No']:
            ruta2 = os.path.join(DIR_COMPROBANTES, s2)
            if os.path.exists(ruta2): st.image(ruta2, caption="Soporte 2", width=150)
    
    st.divider()

# --- LIMPIEZA MANUAL ---
def limpiar_formulario_manual():
    st.session_state.man_nom = ""
    st.session_state.man_cel = ""
    st.session_state.man_abo = 0.0
    st.session_state.man_est = "Nuevo"
    st.session_state.reset_manual += 1

# --- VISTA 1: FORMULARIO CLIENTE (CON MENÚ DE AUTOGESTIÓN) ---
def vista_cliente_principal(pedido_id_param=None):
    st.image("https://cdn-icons-png.flaticon.com/512/2232/2232688.png", width=60)
    st.title("📚 Pedido de Ayuda Escolar")

    # Si viene con ID param (desde link de admin), forzamos edición directa ignorando menú
    if pedido_id_param:
        formulario_pedido(pedido_id_param)
        return

    # MENÚ SUPERIOR
    opcion = st.radio("Seleccione una opción:", 
                      ["• Crear Pedidos", "• Revisar Pedido", "• Editar Pedidos / Confirmar un Pago"], 
                      horizontal=True)
    st.divider()

    inventario = cargar_inventario()
    df_pedidos = cargar_pedidos()

    # ---------------- OPCIÓN 1: CREAR ----------------
    if opcion == "• Crear Pedidos":
        formulario_pedido(None) # None = Nuevo Pedido

    # ---------------- OPCIÓN 2: REVISAR (SOLO LECTURA) ----------------
    elif opcion == "• Revisar Pedido":
        st.subheader("🔍 Consultar mis pedidos")
        cel_busqueda = st.text_input("Ingresa tu número de celular registrado:")
        
        if st.button("Buscar Pedidos"):
            if not cel_busqueda:
                st.warning("Por favor ingresa un número.")
            else:
                # Filtrar normalizando número
                cel_clean = limpiar_numero(cel_busqueda)
                df_pedidos['Cel_Clean'] = df_pedidos['Celular'].apply(limpiar_numero)
                resultados = df_pedidos[df_pedidos['Cel_Clean'] == cel_clean]
                
                if resultados.empty:
                    st.error("No encontramos pedidos con ese número.")
                else:
                    # Lógica: Mostrar todos los que deben plata. Si no debe, mostrar el último.
                    pendientes = resultados[resultados['Saldo'] > 0]
                    
                    if not pendientes.empty:
                        st.info(f"Hemos encontrado {len(pendientes)} pedido(s) con saldo pendiente.")
                        for idx, row in pendientes.iterrows():
                            renderizar_matriz_lectura(row, inventario)
                    else:
                        st.success("¡Estás al día! Aquí está tu último pedido registrado:")
                        ultimo = resultados.iloc[-1]
                        renderizar_matriz_lectura(ultimo, inventario)

    # ---------------- OPCIÓN 3: EDITAR / CONFIRMAR PAGO ----------------
    elif opcion == "• Editar Pedidos / Confirmar un Pago":
        st.subheader("💳 Confirmar Pago / Editar")
        cel_edit = st.text_input("Ingresa tu número de celular para buscar pendientes:")
        
        if st.button("Buscar Pendientes"):
            st.session_state.edit_found = False # Reset
            
        if cel_edit:
             cel_clean = limpiar_numero(cel_edit)
             df_pedidos['Cel_Clean'] = df_pedidos['Celular'].apply(limpiar_numero)
             # SOLO PEDIDOS CON DEUDA
             resultados = df_pedidos[(df_pedidos['Cel_Clean'] == cel_clean) & (df_pedidos['Saldo'] > 0)]
             
             if resultados.empty:
                 st.info("No tienes pedidos pendientes de pago con ese número.")
             else:
                 st.write(f"Encontramos {len(resultados)} pedido(s) pendiente(s).")
                 
                 opciones_dict = {f"{r['ID_Pedido']} - {r['Fecha_Creacion']} (Saldo: ${r['Saldo']:,.0f})": r['ID_Pedido'] for idx, r in resultados.iterrows()}
                 seleccion_txt = st.selectbox("Selecciona el pedido a gestionar:", list(opciones_dict.keys()))
                 
                 if seleccion_txt:
                     id_seleccionado = opciones_dict[seleccion_txt]
                     st.markdown("---")
                     # LLAMAMOS AL FORMULARIO EN MODO EDICIÓN
                     formulario_pedido(id_seleccionado)


# --- SUB-FUNCIÓN: EL FORMULARIO REAL (Reutilizable) ---
def formulario_pedido(pedido_id):
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("El sistema no tiene libros cargados.")
        return

    datos_previos = {}
    es_modificacion = False
    
    if pedido_id:
        df_pedidos = cargar_pedidos()
        # Asegurar tipo string
        pedido_existente = df_pedidos[df_pedidos['ID_Pedido'] == str(pedido_id)]
        if not pedido_existente.empty:
            datos_previos = pedido_existente.iloc[0].to_dict()
            es_modificacion = True
            st.info(f"📝 Gestionando pedido ID: {datos_previos['ID_Pedido']}")

    c1, c2 = st.columns(2)
    nombre = c1.text_input("Nombre Completo", value=datos_previos.get('Cliente', ''))
    celular = c2.text_input("Celular", value=datos_previos.get('Celular', ''))

    st.divider()
    st.subheader("Necesito ayuda en:") 
    
    items, total = componente_seleccion_libros(inventario, "cli", datos_previos.get('Detalle', ''))
    
    st.divider()
    
    col_metrica, col_btn_update = st.columns([2,1])
    col_metrica.metric("Total a Pagar", f"${total:,.0f}")
    col_btn_update.write("")
    if col_btn_update.button("🔄 Actualizar Precio"):
        pass 
    
    st.subheader("Pagos y Soportes")
    tipo = st.radio("Método de Pago:", ["Pago Total", "Abono Parcial"], horizontal=True)
    
    val_abono_anterior = float(datos_previos.get('Abonado', 0))
    if es_modificacion:
        st.write(f"**Abonado anteriormente:** ${val_abono_anterior:,.0f}")
    
    nuevo_abono = st.number_input("Valor a transferir HOY (se sumará al anterior):", min_value=0.0, step=1000.0)
    st.caption("ℹ️ Nota: El valor registrado será validado administrativamente con el soporte adjunto.")
    
    archivo1 = None
    archivo2 = None

    if es_modificacion:
        st.write("---")
        st.markdown("**📂 Cargar Segundo Soporte (Obligatorio si abona)**")
        archivo2 = st.file_uploader("Subir 2do Comprobante", type=['jpg','png','jpeg','pdf'], key="up_soporte_2")
    else:
        st.write("---")
        st.markdown("**📂 Cargar Soporte de Pago**")
        archivo1 = st.file_uploader("Subir Comprobante", type=['jpg','png','jpeg','pdf'], key="up_soporte_1")

    st.write("---")
    
    if st.button("✅ CONFIRMAR Y GUARDAR PEDIDO"):
        with st.spinner("Procesando..."):
            total_abonado_acumulado = val_abono_anterior + nuevo_abono
            
            if not nombre or not celular:
                st.error("⚠️ Falta Nombre o Celular")
            elif total == 0:
                st.error("⚠️ Seleccione al menos un ítem")
            elif (not es_modificacion) and (nuevo_abono == 0):
                st.error("⚠️ Ingrese el valor del abono.")
            elif (not es_modificacion) and (not archivo1):
                st.error("⚠️ Debe subir el comprobante de pago.")
            elif tipo == "Pago Total" and total_abonado_acumulado < total:
                st.error(f"⚠️ Has seleccionado 'Pago Total', pero el valor ingresado (${total_abonado_acumulado:,.0f}) es menor al Total a Pagar (${total:,.0f}).")
            else:
                df = cargar_pedidos()
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                abono_total = total_abonado_acumulado
                saldo = total - abono_total
                
                if es_modificacion:
                    id_actual = str(pedido_id)
                else:
                    id_actual = obtener_nuevo_id(df) 
                
                nombre_arch1 = datos_previos.get('Comprobante', 'No')
                nombre_arch2 = datos_previos.get('Comprobante2', 'No')
                
                if archivo1:
                    nombre_arch1 = guardar_archivo_soporte(archivo1, id_actual)
                if archivo2:
                    nombre_arch2 = guardar_archivo_soporte(archivo2, id_actual, "_2")

                if es_modificacion:
                    idx = df[df['ID_Pedido'] == id_actual].index[0]
                    df.at[idx, 'Ultima_Modificacion'] = fecha
                    df.at[idx, 'Detalle'] = " | ".join(items)
                    df.at[idx, 'Total'] = total
                    df.at[idx, 'Abonado'] = abono_total
                    df.at[idx, 'Saldo'] = saldo
                    if archivo2: df.at[idx, 'Comprobante2'] = nombre_arch2
                    df.at[idx, 'Historial_Cambios'] += f" | Modif: {fecha}"
                    st.session_state.exito_cliente = True 
                    st.session_state.ultimo_pedido_cliente = id_actual
                    st.rerun()
                else:
                    nuevo = {
                        "ID_Pedido": id_actual, "Fecha_Creacion": fecha, "Ultima_Modificacion": fecha,
                        "Cliente": nombre, "Celular": celular, "Detalle": " | ".join(items),
                        "Total": total, "Abonado": abono_total, "Saldo": saldo, "Estado": "Nuevo",
                        "Comprobante": nombre_arch1, "Comprobante2": "No", "Historial_Cambios": "Original"
                    }
                    df = pd.concat([df, pd.DataFrame([nuevo])], ignore_index=True)
                    st.session_state.exito_cliente = True 
                    st.session_state.ultimo_pedido_cliente = id_actual
                
                guardar_pedido_db(df)
                st.rerun()

# --- VISTA DE ÉXITO (CONFIRMACIÓN PEDIDO) ---
def vista_exito_cliente(pedido_id):
    st.balloons() 
    st.success("¡Gracias! Tu pedido ha sido confirmado exitosamente.")
    
    df_pedidos = cargar_pedidos()
    inventario = cargar_inventario()
    # Asegurar string
    pedido = df_pedidos[df_pedidos['ID_Pedido'] == str(pedido_id)]
    
    if not pedido.empty:
        fila = pedido.iloc[0]
        renderizar_matriz_lectura(fila, inventario)

    st.divider()
    if st.button("⬅️ Volver al Inicio"):
        st.session_state.exito_cliente = False
        st.session_state.ultimo_pedido_cliente = None
        st.rerun()

# --- VISTA 2: ADMINISTRADOR ---
def vista_admin():
    url_app = "https://app-libros-escolares-kayrovn4lncquvsdmusqd8.streamlit.app/"
    
    menu = st.sidebar.radio("Navegación:", ["📊 Panel de Ventas", "📦 Inventario de Libros"])

    if menu == "📦 Inventario de Libros":
        st.title("📦 Inventario de Libros")
        
        with st.expander("Subir Excel Masivo"):
            up = st.file_uploader("Excel (Grado, Area, Libro, Costo, Precio Venta)", type=['xlsx','csv'])
            if up:
                try:
                    df_up = pd.read_csv(up) if up.name.endswith('.csv') else pd.read_excel(up)
                    guardar_inventario(df_up)
                    st.success("Cargado y limpiado!")
                except: st.error("Error en archivo")
        
        df = cargar_inventario()
        if not df.empty:
            df_ed = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            if st.button("Guardar Inventario"):
                guardar_inventario(df_ed)
                st.rerun()
            
            st.write("---")
            st.subheader("Resumen Financiero por Grado")
            resumen = df.groupby("Grado")[["Costo", "Precio Venta", "Ganancia"]].sum().reset_index()
            st.dataframe(resumen, use_container_width=True)

    elif menu == "📊 Panel de Ventas":
        st.title("📊 Panel de Ventas")
        df_pedidos = cargar_pedidos()

        st.container(border=True)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📲 Enviar WhatsApp")
            tel = st.text_input("Celular Cliente:", key="tel_wa")
            if tel:
                link_ped = f"{url_app}?rol=cliente"
                msg = f"Hola, haz tu pedido aquí: {link_ped}"
                link_wa = generar_link_whatsapp(tel, msg)
                st.link_button("Enviar Mensaje", link_wa)
        with c2:
            st.subheader("🔗 Copiar Link General")
            st.code(f"{url_app}?rol=cliente", language="text")

        st.divider()

        with st.expander("➕ Registrar Nuevo Pedido Manualmente", expanded=False):
            st.markdown("##### Ingreso Manual")
            col_tit_man, col_btn_clear = st.columns([4, 1])
            with col_btn_clear:
                if st.button("🗑️ Limpiar", type="primary"):
                    limpiar_formulario_manual()
                    st.rerun()

            inventario = cargar_inventario()
            
            if inventario.empty:
                st.warning("⚠️ No hay inventario cargado.")
            else:
                mc1, mc2 = st.columns(2)
                if 'man_nom' not in st.session_state: st.session_state.man_nom = ""
                if 'man_cel' not in st.session_state: st.session_state.man_cel = ""
                if 'man_abo' not in st.session_state: st.session_state.man_abo = 0.0
                if 'man_est' not in st.session_state: st.session_state.man_est = "Nuevo"

                m_nombre = mc1.text_input("Nombre Cliente", key="man_nom")
                m_celular = mc2.text_input("Celular", key="man_cel")
                
                st.write("**Seleccionar Libros:**")
                m_items, m_total = componente_seleccion_libros(inventario, "adm", reset_counter=st.session_state.reset_manual)
                
                st.write("---")
                col_tot, col_abo = st.columns(2)
                col_tot.metric("Total Pedido", f"${m_total:,.0f}")
                
                if col_tot.button("🔄 Calcular Total"): pass

                m_abono = col_abo.number_input("Abono Recibido ($):", min_value=0.0, step=1000.0, key="man_abo")
                m_estado = st.selectbox("Estado del Pedido:", ["Nuevo", "Pagado Total", "Entregado Inmediato"], key="man_est")

                if st.button("💾 GUARDAR PEDIDO MANUAL", key="btn_save_man"):
                    if not m_nombre:
                        st.error("Falta Nombre")
                    elif m_total == 0:
                        st.error("Faltan Libros")
                    else:
                        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        nuevo_id = obtener_nuevo_id(df_pedidos)
                        nuevo_p = {
                            "ID_Pedido": nuevo_id, "Fecha_Creacion": fecha, "Ultima_Modificacion": fecha,
                            "Cliente": m_nombre, "Celular": m_celular, "Detalle": " | ".join(m_items),
                            "Total": m_total, "Abonado": m_abono, "Saldo": m_total - m_abono, "Estado": m_estado,
                            "Comprobante": "Manual/Presencial", "Comprobante2": "No", "Historial_Cambios": "Creado por Admin (Manual)"
                        }
                        df_new = pd.DataFrame([nuevo_p])
                        df_pedidos = pd.concat([df_pedidos, df_new], ignore_index=True)
                        guardar_pedido_db(df_pedidos)
                        st.success(f"✅ Pedido guardado exitosamente! ID: {nuevo_id}")
                        limpiar_formulario_manual()
                        st.rerun()

        st.divider()

        col_title, col_btn = st.columns([2, 2])
        with col_title:
            st.subheader("📋 Listado de Pedidos")
        with col_btn:
            inventario_actual = cargar_inventario()
            if not df_pedidos.empty and not inventario_actual.empty:
                excel_bytes = generar_excel_matriz_bytes(df_pedidos, inventario_actual)
                st.download_button("📥 Descargar Reporte Matriz (Excel)", excel_bytes, "Reporte_Pedidos_Matriz.xlsx")
        
        tipo_vista = st.radio("Modo de Visualización:", ["Vista General (Lista)", "Vista Detallada por Grado (Matriz)"], horizontal=True)

        if not df_pedidos.empty:
            
            if tipo_vista == "Vista General (Lista)":
                filtro = st.text_input("🔍 Buscar Pedido:")
                df_view = df_pedidos
                if filtro:
                    df_view = df_pedidos[df_pedidos['Cliente'].str.contains(filtro, case=False, na=False)]

                edited = st.data_editor(
                    df_view,
                    column_config={
                        "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"], required=True),
                        "Total": st.column_config.NumberColumn(format="$%d"),
                        "Saldo": st.column_config.NumberColumn(format="$%d"),
                        "Comprobante": st.column_config.TextColumn(disabled=True),
                        "Comprobante2": st.column_config.TextColumn(disabled=True)
                    },
                    disabled=["ID_Pedido", "Detalle", "Comprobante", "Comprobante2"],
                    hide_index=True,
                    use_container_width=True
                )
                if st.button("💾 Guardar Cambios (Vista Lista)"):
                    df_pedidos.update(edited)
                    guardar_pedido_db(df_pedidos)
                    st.success("Cambios guardados.")
            
            else:
                st.info("ℹ️ Edita Estados y Saldos.")
                grados_disp = inventario_actual['Grado'].unique()
                grado_sel = st.selectbox("Selecciona el Grado a visualizar:", grados_disp)
                
                if grado_sel:
                    inv_grado = inventario_actual[inventario_actual['Grado'] == grado_sel]
                    mapa_libro_area = {normalizar_clave(k): v for k, v in zip(inv_grado['Libro'], inv_grado['Area'])}
                    areas = inv_grado['Area'].unique()
                    
                    patron = f"[{grado_sel}]"
                    df_grado_view = df_pedidos[df_pedidos['Detalle'].str.contains(patron, regex=False, na=False)].copy()
                    
                    if not df_grado_view.empty:
                        for area in areas:
                            df_grado_view[area] = False
                        
                        for idx, row in df_grado_view.iterrows():
                            items = str(row['Detalle']).split(" | ")
                            for item in items:
                                if patron in item:
                                    area_encontrada = None
                                    match = re.search(r'\((.*?)\)', item)
                                    if match:
                                        posible_area = match.group(1).strip()
                                        for a in areas:
                                            if str(a).strip().lower() == posible_area.lower():
                                                area_encontrada = a
                                                break
                                    
                                    if not area_encontrada:
                                        nombre_raw = item.replace(patron, "").strip()
                                        key_clean = normalizar_clave(nombre_raw)
                                        area_encontrada = mapa_libro_area.get(key_clean)
                                    
                                    if area_encontrada:
                                        df_grado_view.at[idx, area_encontrada] = True
                        
                        cols_to_show = ["ID_Pedido", "Cliente", "Estado", "Total", "Saldo"] + list(areas)
                        column_cfg = {
                            "Estado": st.column_config.SelectboxColumn(options=["Nuevo", "Pagado", "En Impresión", "Entregado", "Anulado"], required=True),
                            "Total": st.column_config.NumberColumn(format="$%d"),
                            "Saldo": st.column_config.NumberColumn(format="$%d"),
                        }
                        
                        edited_matrix = st.data_editor(
                            df_grado_view[cols_to_show],
                            column_config=column_cfg,
                            disabled=["ID_Pedido", "Cliente", "Total"] + list(areas),
                            hide_index=True,
                            use_container_width=True
                        )
                        
                        if st.button("💾 Guardar Cambios"):
                            for i, r in edited_matrix.iterrows():
                                idx_orig = df_pedidos[df_pedidos['ID_Pedido'] == r['ID_Pedido']].index[0]
                                df_pedidos.at[idx_orig, 'Estado'] = r['Estado']
                                df_pedidos.at[idx_orig, 'Saldo'] = r['Saldo']
                            guardar_pedido_db(df_pedidos)
                            st.success("Guardado.")
                    else:
                        st.warning(f"No hay pedidos para {grado_sel}.")

            st.write("---")
            st.subheader("🛠️ Herramientas de Gestión")
            
            filtro_gestion = st.text_input("🔍 Filtrar lista de gestión (Escribe nombre o ID):", placeholder="Ej: 0005 o Juan")
            opciones = df_pedidos['ID_Pedido'] + " - " + df_pedidos['Cliente']
            if filtro_gestion:
                opciones = opciones[opciones.str.contains(filtro_gestion, case=False, na=False)]
            
            p_sel = st.selectbox("Seleccionar Pedido para Gestionar:", opciones)
            
            if p_sel:
                id_sel = p_sel.split(" - ")[0]
                fila = df_pedidos[df_pedidos['ID_Pedido'] == id_sel].iloc[0]
                
                link_edit = f"{url_app}?rol=cliente&pedido_id={id_sel}"
                msg_edit = f"Hola {fila['Cliente']}, aquí puedes ver y actualizar tu pedido: {link_edit}"
                st.link_button("📲 Reenviar Link WhatsApp", generar_link_whatsapp(fila['Celular'], msg_edit))
                
                st.write("---")
                
                col_sop1, col_sop2, col_del = st.columns(3)
                
                with col_sop1:
                    st.write("**Soporte 1 (Inicial):**")
                    arch1 = fila.get('Comprobante', 'No')
                    if arch1 and arch1 not in ["No", "Manual/Presencial"]:
                        ruta1 = os.path.join(DIR_COMPROBANTES, arch1)
                        if os.path.exists(ruta1):
                            st.image(ruta1, width=200)
                        else: st.warning("Archivo no encontrado")
                    else: st.info("Sin soporte inicial")

                with col_sop2:
                    st.write("**Soporte 2 (Adicional):**")
                    arch2 = fila.get('Comprobante2', 'No')
                    if arch2 and arch2 != "No":
                        ruta2 = os.path.join(DIR_COMPROBANTES, arch2)
                        if os.path.exists(ruta2):
                            st.image(ruta2, width=200)
                        else: st.warning("Archivo no encontrado")
                    else: st.info("Sin segundo soporte")

                with col_del:
                    st.write("**Eliminar Pedido:**")
                    confirmar_borrado = st.checkbox("Confirmar eliminación", key=f"del_{id_sel}")
                    if st.button("🗑️ BORRAR", type="primary", disabled=not confirmar_borrado):
                        df_pedidos = df_pedidos[df_pedidos['ID_Pedido'] != id_sel]
                        guardar_pedido_db(df_pedidos)
                        for arch in [arch1, arch2]:
                            if arch and arch not in ["No", "Manual/Presencial"]:
                                p = os.path.join(DIR_COMPROBANTES, arch)
                                if os.path.exists(p): os.remove(p)
                        st.success("Eliminado.")
                        st.rerun()

        else:
            st.info("No hay pedidos registrados aún.")

# --- ROUTER DE SEGURIDAD ---
params = st.query_params
rol = params.get("rol")

# 1. CLIENTES (Acceso Libre)
if rol == "cliente":
    if st.session_state.exito_cliente and st.session_state.ultimo_pedido_cliente:
        vista_exito_cliente(st.session_state.ultimo_pedido_cliente)
    else:
        # Llamamos a la nueva vista con menú, pasando ID si viene en URL
        vista_cliente_principal(params.get("pedido_id"))

# 2. ADMINISTRADOR (Protegido)
else:
    if 'admin_autenticado' not in st.session_state:
        st.session_state.admin_autenticado = False

    if not st.session_state.admin_autenticado:
        st.markdown("<br><br>", unsafe_allow_html=True)
        c_login1, c_login2, c_login3 = st.columns([1,2,1])
        
        with c_login2:
            st.image("https://cdn-icons-png.flaticon.com/512/3064/3064197.png", width=100)
            st.title("🔒 Acceso Administrativo")
            st.info("Por favor ingresa la contraseña para gestionar los pedidos.")
            
            contra_real = st.secrets.get("PASSWORD_ADMIN", "12345")
            contra_input = st.text_input("Contraseña:", type="password")
            
            if st.button("Ingresar al Sistema"):
                if contra_input == str(contra_real):
                    st.session_state.admin_autenticado = True
                    st.success("Acceso concedido")
                    st.rerun()
                else:
                    st.error("⛔ Contraseña incorrecta")

    else:
        if st.sidebar.button("🔒 Cerrar Sesión"):
            st.session_state.admin_autenticado = False
            st.rerun()
            
        vista_admin()