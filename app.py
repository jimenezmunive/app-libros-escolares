import streamlit as st
import pandas as pd
import os
from datetime import datetime
import uuid

# --- CONFIGURACIÓN CLAVE (¡EDITAR ESTO UNA VEZ TENGAS TU LINK!) ---
# Pega aquí el enlace que te da Streamlit al publicar la app.
# Ejemplo: "https://mi-tienda-libros.streamlit.app"
URL_REAL_APP = "https://tu-app-aqui.streamlit.app" 

st.set_page_config(page_title="Gestión Libros Escolares", layout="wide", page_icon="📚")

# --- NOMBRES DE ARCHIVOS ---
FILE_INVENTARIO = 'inventario.csv'
FILE_PEDIDOS = 'base_datos_pedidos.csv'

# --- FUNCIONES DE CARGA Y GUARDADO ---

def cargar_inventario():
    if os.path.exists(FILE_INVENTARIO):
        return pd.read_csv(FILE_INVENTARIO)
    else:
        # Estructura inicial vacía si no hay archivo
        return pd.DataFrame(columns=["Grado", "Area", "Libro", "Costo", "Precio Venta", "Ganancia"])

def guardar_inventario(df):
    # Recalcular Ganancia siempre antes de guardar para evitar errores
    # Aseguramos que sean números
    for col in ['Costo', 'Precio Venta']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['Ganancia'] = df['Precio Venta'] - df['Costo']
    df.to_csv(FILE_INVENTARIO, index=False)

def cargar_pedidos():
    if os.path.exists(FILE_PEDIDOS):
        return pd.read_csv(FILE_PEDIDOS)
    else:
        return pd.DataFrame(columns=[
            "ID_Pedido", "Fecha_Creacion", "Ultima_Modificacion", "Cliente", "Celular", 
            "Detalle", "Total", "Abonado", "Saldo", "Estado", "Comprobante", "Historial_Cambios"
        ])

def guardar_pedido_db(df):
    df.to_csv(FILE_PEDIDOS, index=False)

# --- FUNCIONES AUXILIARES ---
def generar_link_whatsapp(celular, mensaje):
    # Limpieza básica del número
    celular = str(celular).replace(" ", "").replace("+", "").strip()
    if not celular.startswith("57"): # Asumiendo Colombia, ajustar si es otro país
        celular = "57" + celular
    texto_codificado = mensaje.replace(" ", "%20").replace("\n", "%0A")
    return f"https://wa.me/{celular}?text={texto_codificado}"

# --- VISTA: CLIENTE ---
def vista_cliente(pedido_id=None):
    st.title("📚 Formulario de Pedido Escolar")
    
    inventario = cargar_inventario()
    if inventario.empty:
        st.error("El sistema no tiene libros cargados. Contacte al administrador.")
        return

    # Si hay un ID, cargamos los datos previos
    datos_previos = {}
    es_modificacion = False
    
    if pedido_id:
        df_pedidos = cargar_pedidos()
        pedido_existente = df_pedidos[df_pedidos['ID_Pedido'] == pedido_id]
        if not pedido_existente.empty:
            datos_previos = pedido_existente.iloc[0].to_dict()
            es_modificacion = True
            st.info(f"📝 Estás modificando el pedido realizado el: {datos_previos['Fecha_Creacion']}")
            # Calcular días desde la creación
            fecha_creacion = datetime.strptime(datos_previos['Fecha_Creacion'], "%Y-%m-%d %H:%M:%S")
            dias_pasados = (datetime.now() - fecha_creacion).days
            if dias_pasados > 0:
                st.warning(f"⚠️ Han pasado {dias_pasados} días desde tu pedido original.")

    with st.form("form_pedido_cliente"):
        col_datos1, col_datos2 = st.columns(2)
        nombre = col_datos1.text_input("Tu Nombre Completo", value=datos_previos.get('Cliente', ''))
        celular = col_datos2.text_input("Tu Celular (WhatsApp)", value=datos_previos.get('Celular', ''))

        st.divider()
        st.subheader("Selecciona tus libros")
        
        # Agrupar inventario por Grado
        grados = inventario['Grado'].unique()
        seleccion_libros = []
        total_compra = 0
        
        # Lógica para pre-llenar checkboxes si es edición
        detalle_previo = datos_previos.get('Detalle', '')
        
        for grado in grados:
            df_grado = inventario[inventario['Grado'] == grado]
            with st.expander(f"📖 Libros de {grado}"):
                for index, row in df_grado.iterrows():
                    # Clave única para el checkbox
                    key_check = f"{grado}_{row['Area']}_{row['Libro']}"
                    label = f"{row['Area']} - {row['Libro']} (${int(row['Precio Venta']):,})"
                    
                    # Verificar si estaba seleccionado antes
                    checked = False
                    if es_modificacion and f"[{grado}] {row['Libro']}" in detalle_previo:
                        checked = True
                    
                    if st.checkbox(label, key=key_check, value=checked):
                        seleccion_libros.append(f"[{grado}] {row['Libro']}")
                        total_compra += row['Precio Venta']
        
        st.divider()
        st.metric("💰 Total a Pagar", f"${total_compra:,.0f}")
        
        # Sección de Pago
        st.subheader("Confirmación de Pago")
        tipo_pago = st.radio("Método de pago inicial", ["Pago Total", "Abono Parcial", "Pago Contraentrega (Solo si aplica)"], index=0)
        
        val_abono = 0
        if tipo_pago in ["Pago Total", "Abono Parcial"]:
            val_abono = st.number_input("Valor que transfiere hoy:", min_value=0.0, step=1000.0, value=float(datos_previos.get('Abonado', 0)))
            archivo = st.file_uploader("Adjuntar Comprobante de Pago (Imagen/PDF)")
        else:
            archivo = None

        enviar = st.form_submit_button("✅ CONFIRMAR PEDIDO")

        if enviar:
            if not nombre or not celular:
                st.error("Por favor completa tu Nombre y Celular.")
            elif total_compra == 0:
                st.error("No has seleccionado ningún libro.")
            elif (tipo_pago != "Pago Contraentrega") and (val_abono > 0) and (not archivo and not es_modificacion): 
                # Nota: Si es modificación, podriamos permitir no subir archivo si ya pagó, pero por seguridad pedimos soporte si cambia el valor
                st.warning("Recuerda subir el comprobante si realizaste un pago.")
            
            # Procesar guardado
            df_pedidos = cargar_pedidos()
            fecha_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            saldo = total_compra - val_abono
            
            if es_modificacion:
                # Actualizar registro existente
                idx = df_pedidos[df_pedidos['ID_Pedido'] == pedido_id].index
                if not idx.empty:
                    df_pedidos.at[idx[0], 'Ultima_Modificacion'] = fecha_now
                    df_pedidos.at[idx[0], 'Detalle'] = " | ".join(seleccion_libros)
                    df_pedidos.at[idx[0], 'Total'] = total_compra
                    df_pedidos.at[idx[0], 'Abonado'] = val_abono
                    df_pedidos.at[idx[0], 'Saldo'] = saldo
                    df_pedidos.at[idx[0], 'Historial_Cambios'] = str(df_pedidos.at[idx[0], 'Historial_Cambios']) + f" | Modificado el {fecha_now}"
                    if archivo:
                        df_pedidos.at[idx[0], 'Comprobante'] = "Nuevo Comprobante Cargado"
                    
                    guardar_pedido_db(df_pedidos)
                    st.success("✅ Pedido Actualizado Correctamente.")
            else:
                # Nuevo registro
                nuevo_id = str(uuid.uuid4())[:8] # ID corto
                nuevo_pedido = {
                    "ID_Pedido": nuevo_id,
                    "Fecha_Creacion": fecha_now,
                    "Ultima_Modificacion": fecha_now,
                    "Cliente": nombre,
                    "Celular": celular,
                    "Detalle": " | ".join(seleccion_libros),
                    "Total": total_compra,
                    "Abonado": val_abono,
                    "Saldo": saldo,
                    "Estado": "Nuevo - Pendiente Revisión",
                    "Comprobante": "Cargado" if archivo else "Pendiente",
                    "Historial_Cambios": "Creación Original"
                }
                df_new = pd.DataFrame([nuevo_pedido])
                df_pedidos = pd.concat([df_pedidos, df_new], ignore_index=True)
                guardar_pedido_db(df_pedidos)
                st.success(f"✅ ¡Pedido Recibido! Tu ID es: {nuevo_id}")
                st.balloons()

# --- VISTA: ADMINISTRADOR ---
def vista_admin():
    st.sidebar.title("Panel Administrador")
    menu = st.sidebar.radio("Ir a:", ["📊 Gestión de Pedidos", "📦 Inventario de Libros"])

    # ---------------- SECCIÓN INVENTARIO ----------------
    if menu == "📦 Inventario de Libros":
        st.title("📦 Gestión de Inventario")
        
        # 1. Cargar Excel Masivo
        with st.expander("📂 Subir Listado Masivo (Excel)"):
            st.markdown("""
            **Instrucciones:** Sube un archivo Excel (.xlsx) con las columnas exactas:
            `Grado`, `Area`, `Libro`, `Costo`, `Precio Venta`
            *(La columna Ganancia se calcula sola)*
            """)
            archivo_excel = st.file_uploader("Arrastra tu Excel aquí", type=['xlsx', 'xls', 'csv'])
            if archivo_excel:
                try:
                    if archivo_excel.name.endswith('.csv'):
                        df_upload = pd.read_csv(archivo_excel)
                    else:
                        df_upload = pd.read_excel(archivo_excel)
                    
                    # Validar columnas
                    cols_requeridas = ["Grado", "Area", "Libro", "Costo", "Precio Venta"]
                    if all(col in df_upload.columns for col in cols_requeridas):
                        # Calcular ganancia y guardar
                        guardar_inventario(df_upload)
                        st.success("¡Base de datos de libros actualizada correctamente!")
                    else:
                        st.error(f"El archivo debe tener las columnas: {cols_requeridas}")
                except Exception as e:
                    st.error(f"Error al leer el archivo: {e}")

        st.divider()
        
        # 2. Editor y Visualización
        df_inv = cargar_inventario()
        
        if not df_inv.empty:
            st.subheader("Editor de Inventario")
            # Permitir edición directa
            df_editado = st.data_editor(df_inv, num_rows="dynamic", use_container_width=True)
            
            if st.button("💾 Guardar Cambios Manuales"):
                guardar_inventario(df_editado)
                st.success("Inventario actualizado.")
                st.rerun()
            
            st.divider()
            
            # 3. Totales por Grado (Requerimiento Específico)
            st.subheader("📈 Rentabilidad por Grado")
            # Agrupar y sumar
            resumen = df_inv.groupby("Grado")[["Costo", "Precio Venta", "Ganancia"]].sum().reset_index()
            # Formato de moneda para visualización
            st.dataframe(resumen.style.format({
                "Costo": "${:,.0f}", 
                "Precio Venta": "${:,.0f}", 
                "Ganancia": "${:,.0f}"
            }), use_container_width=True)
            
        else:
            st.info("El inventario está vacío. Sube un Excel o añade filas manualmente.")

    # ---------------- SECCIÓN PEDIDOS ----------------
    elif menu == "📊 Gestión de Pedidos":
        st.title("Panel de Ventas y Pedidos")
        
        df_pedidos = cargar_pedidos()
        
        # --- NOTIFICACIONES / ALERTAS ---
        nuevos = len(df_pedidos[df_pedidos['Estado'].str.contains("Nuevo", na=False)])
        if nuevos > 0:
            st.warning(f"🔔 Tienes {nuevos} pedidos NUEVOS sin revisar.")

        # --- HERRAMIENTA DE CREACIÓN Y ENVÍO ---
        st.container(border=True)
        col_tool1, col_tool2 = st.columns(2)
        
        with col_tool1:
            st.subheader("📲 Enviar Link a Cliente (Nuevo Pedido)")
            tel_nuevo = st.text_input("Celular Cliente (Nuevo):")
            if tel_nuevo:
                link_gen = f"{URL_REAL_APP}?rol=cliente"
                mensaje_nuevo = f"Hola! Ingresa a este enlace para realizar tu pedido de libros escolares: {link_gen}"
                link_wa = generar_link_whatsapp(tel_nuevo, mensaje_nuevo)
                st.markdown(f"[➡️ **Enviar Link por WhatsApp**]({link_wa})", unsafe_allow_html=True)
            
            st.markdown("---")
            st.caption("👇 Copia este enlace para enviarlo a grupos o redes:")
            st.code(f"{URL_REAL_APP}?rol=cliente", language="text")

        with col_tool2:
            st.subheader("📝 Crear Pedido Manualmente")
            if st.button("Abrir Formulario de Creación (Admin)"):
                # Usamos la session state para abrir un modal o redirigir
                # Por simplicidad, abrimos el link en una pestaña nueva simulando ser cliente
                link_manual = f"{URL_REAL_APP}?rol=cliente"
                st.markdown(f"**[Click aquí para llenar el pedido tú mismo]({link_manual})**", unsafe_allow_html=True)

        st.divider()
        
        # --- BASE DE DATOS Y GESTIÓN ---
        st.subheader("📋 Base de Datos de Pedidos")
        
        if not df_pedidos.empty:
            # Filtros
            filtro = st.text_input("🔍 Buscar por Nombre o Celular:")
            if filtro:
                df_view = df_pedidos[df_pedidos['Cliente'].str.contains(filtro, case=False, na=False) | df_pedidos['Celular'].str.contains(filtro, na=False)]
            else:
                df_view = df_pedidos

            # Edición de Estado Directa
            st.write("Edita el estado directamente en la tabla:")
            edited_df = st.data_editor(
                df_view,
                column_config={
                    "Comprobante": st.column_config.TextColumn("Pago", disabled=True),
                    "Estado": st.column_config.SelectboxColumn(
                        "Estado",
                        options=["Nuevo - Pendiente Revisión", "Confirmado - Abono", "Pagado Total", "En Impresión", "Entregado", "Anulado"],
                        required=True
                    ),
                    "Total": st.column_config.NumberColumn(format="$%d"),
                    "Saldo": st.column_config.NumberColumn(format="$%d"),
                },
                disabled=["ID_Pedido", "Fecha_Creacion", "Historial_Cambios"], # Campos que admin no debe tocar por error
                hide_index=True
            )
            
            if st.button("💾 Guardar Cambios de Estado"):
                # Actualizar el DF original con los cambios
                df_pedidos.update(edited_df)
                guardar_pedido_db(df_pedidos)
                st.success("Base de datos actualizada.")
            
            st.divider()
            
            # --- ACCIONES AVANZADAS SOBRE UN PEDIDO ---
            st.subheader("🔧 Acciones sobre un Pedido Específico")
            pedido_select_id = st.selectbox("Selecciona un Pedido para gestionar:", df_pedidos['ID_Pedido'].astype(str) + " - " + df_pedidos['Cliente'])
            
            if pedido_select_id:
                # Extraer ID real
                id_real = pedido_select_id.split(" - ")[0]
                fila_pedido = df_pedidos[df_pedidos['ID_Pedido'] == id_real].iloc[0]
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.info(f"**Cliente:** {fila_pedido['Cliente']}")
                    st.write(f"**Saldo:** ${fila_pedido['Saldo']:,}")
                with c2:
                    # Botón para reenviar link de edición
                    link_edit = f"{URL_REAL_APP}?rol=cliente&pedido_id={id_real}"
                    msg_edit = f"Hola {fila_pedido['Cliente']}, aquí tienes el enlace para revisar o modificar tu pedido: {link_edit}"
                    wa_edit = generar_link_whatsapp(fila_pedido['Celular'], msg_edit)
                    st.markdown(f"[📲 **Enviar Link de Modificación**]({wa_edit})", unsafe_allow_html=True)
                with c3:
                    st.write("**Historial:**")
                    st.caption(fila_pedido['Historial_Cambios'])

        else:
            st.info("No hay pedidos registrados.")

# --- CONTROL DE FLUJO PRINCIPAL ---
params = st.query_params
rol = params.get("rol", "admin")
pedido_id_url = params.get("pedido_id", None)

if rol == "cliente":
    vista_cliente(pedido_id_url)
else:
    vista_admin()