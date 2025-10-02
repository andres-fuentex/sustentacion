import streamlit as st
import geopandas as gpd
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from io import BytesIO
import base64
import streamlit.components.v1 as components
import json
import pydeck as pdk

import os



if os.environ.get("STREAMLIT_RUNNING") == "true":
    import plotly.io as pio
    pio.kaleido.scope.chromium_args = (
        "--headless",
        "--no-sandbox",
        "--single-process",
        "--disable-gpu"
    )
    pio.kaleido.scope.use_chromium()



# --- Configuración de la Página ---
st.set_page_config(page_title="AVM Bogotá APP", page_icon="🏠", layout="centered")
st.title("🏠 AVM Bogotá - Análisis de Manzanas")

# --- Función cacheada para la carga de datos (con manejo de errores y reintentos) ---
@st.cache_data
def cargar_datasets():
    datasets = {
        "localidades": "https://github.com/andres-fuentex/tfm-avm-bogota/raw/main/datos_visualizacion/datos_geograficos_geo/dim_localidad.geojson",
        "areas": "https://github.com/andres-fuentex/tfm-avm-bogota/raw/main/datos_visualizacion/datos_geograficos_geo/dim_area.geojson",
        "manzanas": "https://github.com/andres-fuentex/tfm-avm-bogota/raw/main/datos_visualizacion/datos_geograficos_geo/tabla_hechos.geojson",
        "transporte": "https://github.com/andres-fuentex/tfm-avm-bogota/raw/main/datos_visualizacion/datos_geograficos_geo/dim_transporte.geojson",
        "colegios": "https://github.com/andres-fuentex/tfm-avm-bogota/raw/main/datos_visualizacion/datos_geograficos_geo/dim_colegios.geojson"
    }

    dataframes = {}
    total = len(datasets)
    progress_bar = st.progress(0, text="Iniciando carga de datos...")

    for idx, (nombre, url) in enumerate(datasets.items(), start=1):
        progress_text = f"Cargando {nombre} ({idx}/{total})..."
        progress_bar.progress(idx / total, text=progress_text)
        
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Leer el contenido como JSON usando la librería json
                geojson_data = json.loads(response.text)
                
                # Crear el GeoDataFrame desde el JSON
                dataframes[nombre] = gpd.GeoDataFrame.from_features(geojson_data["features"], crs="EPSG:4326")
                break  # Si la carga tiene éxito, salir del bucle
            
            except requests.exceptions.RequestException as e:
                st.warning(f"Intento {attempt + 1}/{max_retries} fallido al cargar {nombre}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)  # Esperar antes de reintentar
                else:
                    st.error(f"Error al cargar {nombre} después de {max_retries} intentos: {e}")
                    return None  # Detener la carga si no se puede descargar después de varios intentos
            except json.JSONDecodeError as e:
                st.error(f"Error al decodificar JSON para {nombre}: {e}. Detalle: {e}")
                return None # No reintentar si el problema es el JSON
            except Exception as e:
                st.error(f"Error al procesar {nombre}: {e}")
                return None

    progress_bar.empty()
    return dataframes

# --- Control de flujo ---
if "step" not in st.session_state:
    st.session_state.step = 1

# --- Bloque 1: Carga de datos ---
if st.session_state.step == 1:
    st.markdown(
        """
        Bienvenido al sistema de valorización automatizada de manzanas catastrales en Bogotá.
        """
    )
    with st.spinner('Cargando datasets...'):
        dataframes = cargar_datasets()

    if dataframes:  # Verificar que la carga de datos fue exitosa
        st.success('✅ Todos los datos han sido cargados correctamente.')

        if st.button("Iniciar Análisis"):
            for nombre, df in dataframes.items():
                st.session_state[nombre] = df
            st.session_state.step = 2
            st.rerun()
    else:
        st.error("❌ Error al cargar los datasets. Por favor, revise las URLs o la conexión a Internet.")

# --- Bloque 2: Selección de Localidad ---
elif st.session_state.step == 2:
    st.header("🌆 Selección de Localidad")
    st.markdown("Haz clic en la localidad que te interesa:")

    localidades = st.session_state.localidades
    if localidades is None:
        st.error("❌ No se cargaron los datos de las localidades. Por favor, reinicia la aplicación.")
        st.stop()

    bounds = localidades.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    mapa = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

    folium.GeoJson(
        localidades,
        style_function=lambda feature: {"fillColor": "#3388ff", "color": "black", "weight": 1, "fillOpacity": 0.2},
        highlight_function=lambda feature: {"weight": 2, "color": "red"},
        tooltip=folium.GeoJsonTooltip(fields=["nombre_localidad"], labels=False)
    ).add_to(mapa)

    result = st_folium(mapa, width=700, height=500, returned_objects=["last_clicked"])

    clicked = result.get("last_clicked")
    if clicked and "lat" in clicked and "lng" in clicked:
        punto = Point(clicked["lng"], clicked["lat"])
        for _, row in st.session_state.localidades.iterrows():
            if row["geometry"].contains(punto):
                st.session_state.localidad_clic = row["nombre_localidad"]
                break
        else:
            st.session_state.localidad_clic = None
            st.warning("⚠️ No se encontró ninguna localidad en la ubicación seleccionada.") # Mensaje mejorado
    else:
        st.session_state.localidad_clic = None

    if "localidad_clic" in st.session_state and st.session_state.localidad_clic:
        st.text_input("✅ Localidad seleccionada", value=st.session_state.localidad_clic, disabled=True)
        if st.button("✅ Confirmar selección"):
            st.session_state.localidad_sel = st.session_state.localidad_clic
            st.session_state.step = 3
            st.rerun()

    if st.button("🔄 Volver al Inicio"):
        st.session_state.step = 1
        st.rerun()

    if "localidad_sel" not in st.session_state:
        st.info("Selecciona una localidad y confírmala para continuar.")

# --- Bloque 3: Selección de Manzana ---
# --- Bloque 3: Selección de Manzana ---
# --- Bloque 3: Selección de Manzana con Copia Manual ---
elif st.session_state.step == 3:
    st.subheader(f"🏘️ Análisis y Selección de Manzana en {st.session_state.localidad_sel}")

    import streamlit.components.v1 as components
    import geopandas as gpd
    import plotly.express as px
    import json
    import plotly.io as pio
    from io import BytesIO
   

    localidades = st.session_state.localidades
    areas = st.session_state.areas
    manzanas = st.session_state.manzanas

    localidad_sel = st.session_state.localidad_sel
    cod_localidad = localidades[localidades["nombre_localidad"] == localidad_sel]["num_localidad"].values[0]

    # --- Primer mapa (Plotly): Localidad resaltada ---
    st.markdown("### 🗺️ Localidad Seleccionada (Mapa de Referencia)")
    localidades["seleccionada"] = localidades["nombre_localidad"] == localidad_sel
    bounds = localidades[localidades["seleccionada"]].total_bounds
    center = {"lon": (bounds[0] + bounds[2]) / 2, "lat": (bounds[1] + bounds[3]) / 2}

    fig_localidad = px.choropleth_mapbox(
        localidades,
        geojson=localidades.geometry,
        locations=localidades.index,
        color="seleccionada",
        color_discrete_map={True: "red", False: "lightgray"},
        hover_name="nombre_localidad",
        mapbox_style="carto-positron",
        center=center,
        zoom=10
    )
    fig_localidad.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig_localidad, use_container_width=True)

    # Guardar imagen del mapa de localidad para el informe
    buffer_localidad = BytesIO()
    pio.write_image(fig_localidad, buffer_localidad, format='png', engine='kaleido')
    st.session_state.buffer_localidad = buffer_localidad

    # --- Preparación de manzanas + colores ---
    areas_sel = areas[areas["num_localidad"] == cod_localidad].copy()
    manzanas_sel = manzanas[manzanas["num_localidad"] == cod_localidad].copy()

    if manzanas_sel.empty:
        st.warning("⚠️ No se encontraron manzanas para la localidad seleccionada.")
        if st.button("🔙 Volver a Selección de Localidad"):
            st.session_state.step = 2
            st.rerun()
    else:
        st.markdown("""
        ### 🖱️ Haz clic sobre la manzana para seleccionarla
        ✅ El código de la manzana seleccionada aparecerá en la caja de abajo
        ✅ ¡Copia el código y pégalo en el campo para confirmar!
        """)

        if not areas_sel.empty:
            manzanas_sel = manzanas_sel.merge(
                areas_sel[["id_area", "uso_pot_simplificado"]],
                on="id_area",
                how="left"
            )
        else:
            manzanas_sel["uso_pot_simplificado"] = "Sin clasificación"

        manzanas_sel["uso_pot_simplificado"] = manzanas_sel["uso_pot_simplificado"].fillna("Sin clasificación")

        cats = manzanas_sel["uso_pot_simplificado"].unique().tolist()
        palette = px.colors.qualitative.Plotly
        color_map = {cat: palette[i % len(palette)] for i, cat in enumerate(cats)}
        if "Sin clasificación" not in color_map:
            color_map["Sin clasificación"] = "#2b2b2b"

        manzanas_sel["color"] = manzanas_sel["uso_pot_simplificado"].apply(lambda x: color_map.get(x, "#2b2b2b"))

        # Construir el GeoJSON con color y preparar mapa
        manzanas_features = []
        for _, row in manzanas_sel.iterrows():
            manzanas_features.append({
                "type": "Feature",
                "geometry": json.loads(gpd.GeoSeries([row["geometry"]]).to_json())["features"][0]["geometry"],
                "properties": {
                    "id_manzana_unif": row["id_manzana_unif"],
                    "color": row["color"]
                }
            })

        manzanas_geojson = {
            "type": "FeatureCollection",
            "features": manzanas_features
        }

        geojson_text = json.dumps(manzanas_geojson)

        # Mostrar mapa y caja HTML
        components.html(f"""
            <div id="map" style="height: 500px;"></div>
            <p><b>🔎 Código de la manzana seleccionada (¡copia este valor!):</b></p>
            <input type="text" id="selected_id_input" value="" style="width: 100%; padding: 5px;" readonly>

            <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>

            <script>
                const map = L.map('map').setView([{center['lat']}, {center['lon']}], 13);
                L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    maxZoom: 18,
                    attribution: '© OpenStreetMap contributors'
                }}).addTo(map);

                const manzanas = {geojson_text};

                function style(feature) {{
                    return {{
                        fillColor: feature.properties.color,
                        weight: 1,
                        opacity: 1,
                        color: 'black',
                        fillOpacity: 0.5
                    }};
                }}

                function highlightStyle() {{
                    return {{
                        fillColor: 'orange',
                        weight: 2,
                        color: 'red',
                        fillOpacity: 0.7
                    }};
                }}

                let selectedLayer = null;

                function onEachFeature(feature, layer) {{
                    layer.on({{
                        click: function(e) {{
                            if (selectedLayer) {{
                                geojson.resetStyle(selectedLayer);
                            }}
                            selectedLayer = layer;
                            layer.setStyle(highlightStyle());
                            document.getElementById("selected_id_input").value = feature.properties.id_manzana_unif;
                        }}
                    }});
                layer.bindTooltip("Manzana: " + feature.properties.id_manzana_unif);
                }}

                const geojson = L.geoJSON(manzanas, {{
                    style: style,
                    onEachFeature: onEachFeature
                }}).addTo(map);

                map.fitBounds(geojson.getBounds());
            </script>
        """, height=620)

        # Confirmación manual (el usuario copia el valor)
    manzana_input = st.text_input("✅ Pega aquí el código de la manzana seleccionada para confirmar:")

    if st.button("✅ Confirmar Manzana Seleccionada"):
        if manzana_input:
            st.session_state.manzana_sel = manzana_input
            st.session_state.manzanas_localidad_sel = manzanas_sel
            st.session_state.step = 4
            st.rerun()
        else:
            st.warning("Debes pegar el código de la manzana seleccionada.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔙 Volver a Selección de Localidad"):
            st.session_state.step = 2
            st.rerun()
    with col2:
        if st.button("🔄 Volver al Inicio"):
            st.session_state.step = 1
            st.rerun()
### OJO CON ESTE CAMBIO
        st.session_state.manzanas_localidad_sel = manzanas_sel
        st.session_state.color_map = color_map

    def hexToRgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))



# --- Bloque 4: Análisis Espacial de la Manzana Seleccionada ---
elif st.session_state.step == 4:
    st.subheader("🗺️ Análisis Contextual de la Manzana Seleccionada")

    import geopandas as gpd
    import plotly.graph_objects as go
    import pandas as pd
    from shapely.geometry import MultiPoint, Point
    from io import BytesIO
    import plotly.io as pio

    manzanas = st.session_state.manzanas
    transporte = st.session_state.transporte
    colegios = st.session_state.colegios
    id_manzana = st.session_state.manzana_sel
    
    manzana_sel = manzanas[manzanas["id_manzana_unif"] == id_manzana]

    if manzana_sel.empty:
        st.warning("⚠️ No se encontraron datos para la manzana seleccionada.")
        if st.button("🔙 Volver a Selección de Manzana"):
            st.session_state.step = 3
            st.rerun()
    else:
        # --- 1. Preparar la Manzana y el Centroide ---
        manzana_proj = manzana_sel.to_crs(epsg=3116)
        centroide = manzana_proj.geometry.centroid.to_crs(epsg=4326).iloc[0]
        lon0, lat0 = centroide.x, centroide.y

        # --- 2. Contexto de TRANSPORTE ---
        st.markdown("### 🚇 Contexto de Transporte (Buffer 800m)")
        
        buffer_transporte_proj = manzana_proj.buffer(800)
        buffer_transporte_wgs = gpd.GeoSeries([buffer_transporte_proj.iloc[0]], crs=3116).to_crs(epsg=4326).iloc[0]
        
        fig_transporte = go.Figure(go.Scattermapbox(
            lat=list(buffer_transporte_wgs.exterior.xy[1]),
            lon=list(buffer_transporte_wgs.exterior.xy[0]),
            mode='lines', fill='toself', name='Buffer 800m',
            fillcolor='rgba(255,0,0,0.1)', line=dict(color='red')
        ))

        fig_transporte.add_trace(go.Scattermapbox(
            lat=list(manzana_sel.geometry.iloc[0].exterior.xy[1]),
            lon=list(manzana_sel.geometry.iloc[0].exterior.xy[0]),
            mode='lines', fill='toself', name='Manzana',
            fillcolor='rgba(0,128,0,0.3)', line=dict(color='darkgreen')
        ))

        id_combi = manzana_sel["id_combi_acceso"].iloc[0]
        if pd.notna(id_combi):
            multipunto_transporte = transporte.loc[transporte["id_combi_acceso"] == id_combi, "geometry"]
            if not multipunto_transporte.empty:
                puntos = list(multipunto_transporte.iloc[0].geoms)
                fig_transporte.add_trace(go.Scattermapbox(
                    lat=[p.y for p in puntos], lon=[p.x for p in puntos],
                    mode='markers', name='Estaciones', marker=dict(color='red', size=10)
                ))

        fig_transporte.update_layout(
            mapbox_style="carto-positron", mapbox_center={"lat": lat0, "lon": lon0}, mapbox_zoom=14,
            margin={"r": 0, "t": 40, "l": 0, "b": 0}, title="Contexto de Transporte"
        )
        st.plotly_chart(fig_transporte, use_container_width=True)
        buffer_img_transporte = BytesIO()
        pio.write_image(fig_transporte, buffer_img_transporte, format='png', engine='kaleido')
        st.session_state.buffer_transporte = buffer_img_transporte

        # --- 3. Contexto EDUCATIVO ---
        st.markdown("### 🏫 Contexto Educativo (Buffer 1000m)")
        buffer_colegios_proj = manzana_proj.buffer(1000)
        buffer_colegios_wgs = gpd.GeoSeries([buffer_colegios_proj.iloc[0]], crs=3116).to_crs(epsg=4326).iloc[0]

        fig_colegios = go.Figure(go.Scattermapbox(
            lat=list(buffer_colegios_wgs.exterior.xy[1]),
            lon=list(buffer_colegios_wgs.exterior.xy[0]),
            mode='lines', fill='toself', name='Buffer 1000m',
            fillcolor='rgba(0,0,255,0.1)', line=dict(color='blue')
        ))

        id_colegios = manzana_sel["id_com_colegios"].iloc[0]
        if pd.notna(id_colegios):
            colegios_filtered = colegios[colegios["id_com_colegios"] == id_colegios]
            if not colegios_filtered.empty:
                puntos_colegios = []
                for geom in colegios_filtered.geometry:
                    if isinstance(geom, MultiPoint):
                        puntos_colegios.extend(list(geom.geoms))
                    elif isinstance(geom, Point):
                        puntos_colegios.append(geom)

                if puntos_colegios:
                    lat_col,lon_col = zip(*[(point.y,point.x) for point in puntos_colegios])
                    fig_colegios.add_trace(go.Scattermapbox(
                        lat=lat_col,lon=lon_col,
                        mode='markers', name='Colegios', marker=dict(color='blue', size=10)
                    ))
        fig_colegios.update_layout(
            mapbox_style="carto-positron", mapbox_center={"lat": lat0, "lon": lon0}, mapbox_zoom=14,
            margin={"r": 0, "t": 40, "l": 0, "b": 0}, title="Contexto Educativo"
        )
        st.plotly_chart(fig_colegios, use_container_width=True)

        buffer_img_colegios = BytesIO()
        pio.write_image(fig_colegios, buffer_img_colegios, format='png', engine='kaleido')
        st.session_state.buffer_colegios = buffer_img_colegios
    

    # Navegación
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔙 Volver a Selección de Manzana"):
            st.session_state.step = 3
            st.rerun()
    with col2:
        if st.button("🔄 Volver al Inicio"):
            st.session_state.step = 1
            st.rerun()
    with col3:
        if st.button("➡️ Continuar al Análisis Comparativo", disabled=manzana_sel.empty):
            st.session_state.step = 5
            st.session_state.buffer_transporte = buffer_img_transporte
            st.session_state.buffer_colegios = buffer_img_colegios
            st.session_state.manzana_seleccionada_df = manzana_sel
            st.rerun()

            # --- Bloque 5: Análisis Comparativo y Proyección del Valor m² ---
elif st.session_state.step == 5:
    st.subheader("📊 Análisis Comparativo y Proyección del Valor m²")

    import pandas as pd
    from io import BytesIO
    import plotly.express as px
    import plotly.graph_objects as go
    import plotly.io as pio

    localidades = st.session_state.localidades
    manzanas = st.session_state.manzanas
    areas = st.session_state.areas
    manzana_id = st.session_state.manzana_sel
    if "colegios" in st.session_state:
        colegios = st.session_state.colegios
    if "transporte" in st.session_state:
        transporte = st.session_state.transporte

    manzanas_sel = st.session_state.manzanas_localidad_sel.copy()
    color_map = st.session_state.color_map
    manzana_sel = manzanas_sel[manzanas_sel["id_manzana_unif"] == manzana_id]

    if "uso_pot_simplificado_y" in manzanas_sel.columns and "uso_pot_simplificado_x" in manzanas_sel.columns:
        manzanas_sel["uso_pot_simplificado"] = manzanas_sel["uso_pot_simplificado_y"].combine_first(manzanas_sel["uso_pot_simplificado_x"]).fillna("Sin clasificación POT")
    elif "uso_pot_simplificado" in manzanas_sel.columns:
        manzanas_sel["uso_pot_simplificado"] = manzanas_sel["uso_pot_simplificado"].fillna("Sin clasificación POT")
    else:
        manzanas_sel["uso_pot_simplificado"] = "Sin clasificación POT"

    cod_localidad = manzana_sel["num_localidad"].values[0]
    nombre_localidad = localidades.loc[localidades["num_localidad"] == cod_localidad, "nombre_localidad"].values[0]

    st.markdown("### 📈 Comparativo de valor m²")

    id_area_manzana = manzana_sel["id_area"].values[0]

    if pd.notna(id_area_manzana):
        manzanas_area = manzanas_sel[manzanas_sel["id_area"] == id_area_manzana]
    else:
        manzanas_area = manzanas_sel[manzanas_sel["id_area"].isna()]

    promedio_area = manzanas_area["valor_m2"].mean() if not manzanas_area.empty else 0
    valor_manzana = manzana_sel["valor_m2"].values[0]

    buffer_300 = manzana_sel.to_crs(epsg=3116).buffer(300).to_crs(epsg=4326)
    manzanas_buffer = manzanas_sel[manzanas_sel.geometry.intersects(buffer_300.iloc[0])]
    promedio_buffer = manzanas_buffer["valor_m2"].mean() if not manzanas_buffer.empty else 0

    fig = go.Figure()
    fig.add_trace(go.Bar(x=["Manzana seleccionada"], y=[valor_manzana], text=[f"${valor_manzana:,.0f}"], textposition="outside", marker_color='rgba(0, 102, 204, 0.8)'))
    fig.add_trace(go.Bar(x=["Promedio área POT"] if pd.notna(id_area_manzana) else ["Promedio sin área"], y=[promedio_area], text=[f"${promedio_area:,.0f}"], textposition="outside", marker_color='rgba(0, 102, 204, 0.6)'))
    fig.add_trace(go.Bar(x=["Promedio 300m"], y=[promedio_buffer], text=[f"${promedio_buffer:,.0f}"], textposition="outside", marker_color='rgba(0, 102, 204, 0.4)'))

    fig.update_layout(title="Comparativo de valor m² respecto al área POT y 300m a la redonda", yaxis_title="Valor por metro cuadrado", barmode="group", template="simple_white", margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)

    st.session_state.buffer_valorm2 = BytesIO(pio.to_image(fig, format='png'))

    st.markdown("### 🥧 Distribución de usos POT en 500m")

    buffer_uso = manzana_sel.to_crs(epsg=3116).buffer(500).to_crs(epsg=4326)
    manzanas_buffer_uso = manzanas_sel[manzanas_sel.geometry.intersects(buffer_uso.iloc[0])]

    if "uso_pot_simplificado" not in manzanas_buffer_uso.columns:
        manzanas_buffer_uso["uso_pot_simplificado"] = "Sin clasificación POT"

    conteo_uso = manzanas_buffer_uso["uso_pot_simplificado"].value_counts().reset_index()
    conteo_uso.columns = ["uso", "cantidad"]

    


    if not conteo_uso.empty:
        colores = [color_map.get(uso, "gray") for uso in conteo_uso["uso"]]
        fig_pie = px.pie(conteo_uso, values="cantidad", names="uso", color_discrete_sequence=colores, title=f"Distribución de usos POT en buffer de 500m\nManzana {manzana_id}")
        fig_pie.update_traces(textinfo='percent+label', textfont_size=14)
        fig_pie.update_layout(template="simple_white", margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_pie, use_container_width=True)
        st.session_state.buffer_dist_pot = BytesIO(pio.to_image(fig_pie, format='png'))
    else:
        st.warning("⚠️ No se encontraron manzanas con clasificación POT dentro del buffer de 500m.")

    st.markdown("### 📈 Proyección del valor m² para los próximos años")

    serie_proyeccion = manzana_sel[["valor_m2", "valor_2025_s1", "valor_2025_s2", "valor_2026_s1", "valor_2026_s2"]].values.flatten()
    fechas = ["2024-S2", "2025-S1", "2025-S2", "2026-S1", "2026-S2"]

    # --- Guardar variables clave en session_state para el informe ---
    st.session_state.nombre_localidad = nombre_localidad
    st.session_state.promedio_area = promedio_area
    st.session_state.promedio_buffer = promedio_buffer


    if not conteo_uso.empty:
        uso_pot_mayoritario = conteo_uso.iloc[0]["uso"]
        st.session_state.uso_pot_mayoritario = uso_pot_mayoritario
    else:
        st.session_state.uso_pot_mayoritario = "Sin clasificación POT"
    
    st.session_state.buffer_mapa_pot = st.session_state.buffer_dist_pot



    ## OJO CON ESTE BLOQUE
    import plotly.express as px
    import plotly.io as pio
    from io import BytesIO

    manzanas_localidad = st.session_state.manzanas_localidad_sel.copy()
    color_map = st.session_state.color_map

    import pandas as pd

    # Crear la ficha estilizada para el informe
    ficha_estilizada = pd.DataFrame({
    "ID Manzana": [manzana_id],
    "Localidad": [nombre_localidad],
    "Estrato": [manzana_sel["estrato"].values[0]],
    "Valor m²": [f"${valor_manzana:,.0f}"],
    "Prom. Área POT": [f"${promedio_area:,.0f}"],
    "Prom. 300m": [f"${promedio_buffer:,.0f}"],
    "Rentabilidad": [manzana_sel["rentabilidad"].values[0]]
    })

    st.session_state.ficha_estilizada = ficha_estilizada


    
    if not any(pd.isna(serie_proyeccion)):
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=fechas, y=serie_proyeccion, mode="lines+markers+text", line=dict(color="royalblue", width=3), marker=dict(size=8), text=[f"${v:,.0f}" for v in serie_proyeccion], textposition="top center", textfont=dict(size=14), name="Proyección valor m²"))
        fig_line.update_layout(title=f"Evolución Proyectada del Valor m² - Manzana {manzana_id}", xaxis_title="Periodo", yaxis_title="Valor m²", template="simple_white", margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_line, use_container_width=True)
        st.session_state.buffer_proyeccion = BytesIO(pio.to_image(fig_line, format='png'))
    else:
        st.warning("⚠️ La información de proyección del valor m² no está completa para esta manzana.")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔙 Volver al Análisis de Transporte y Educación"):
            st.session_state.step = 4
            st.rerun()
    with col2:
        if st.button("➡️ Continuar al Análisis de Seguridad"):
            st.session_state.step = 6
            st.rerun()

    # BLOQUE 6
elif st.session_state.step == 6:
    st.subheader("🔎 Contexto de Seguridad por Localidad")
    import plotly.express as px
    from io import BytesIO
    import plotly.io as pio

    localidades = st.session_state.localidades
    manzana_sel = st.session_state.manzanas_localidad_sel[
        st.session_state.manzanas_localidad_sel["id_manzana_unif"] == st.session_state.manzana_sel
    ]

    if manzana_sel.empty:
        st.warning("⚠️ No se encontró información de la manzana seleccionada.")
        if st.button("🔙 Volver al Bloque Anterior"):
            st.session_state.step = 5
            st.rerun()
    else:
        cod_loc = manzana_sel["num_localidad"].values[0]

        df_seguridad = localidades[["nombre_localidad", "num_localidad", "cantidad_delitos", "nivel_riesgo_delictivo"]].copy()
        df_seguridad["es_localidad_actual"] = df_seguridad["num_localidad"] == cod_loc
        df_seguridad["etiqueta"] = df_seguridad.apply(
            lambda row: row["nivel_riesgo_delictivo"] if row["es_localidad_actual"] else "", axis=1
        )
        df_seguridad.sort_values("cantidad_delitos", ascending=True, inplace=True)

        fig = px.bar(
            df_seguridad,
            x="cantidad_delitos",
            y="nombre_localidad",
            orientation="h",
            color="es_localidad_actual",
            color_discrete_map={True: "darkgreen", False: "rgba(0,100,0,0.3)"},
            text="etiqueta"
        )

        fig.update_traces(textposition="outside")
        fig.update_layout(
            title="Contexto de seguridad por localidad\nFuente: Secretaría Distrital de Seguridad y Convivencia",
            xaxis_title="Cantidad de delitos",
            yaxis_title=" ",
            showlegend=False,
            template="simple_white",
            margin=dict(l=0, r=0, t=40, b=0)
        )
        fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(fig, use_container_width=True)

        st.session_state.buffer_seguridad = BytesIO()
        pio.write_image(fig, st.session_state.buffer_seguridad, format='png') # Correcto: Guarda la figura en el buffer
        st.session_state.df_seguridad = df_seguridad


        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔙 Volver al Análisis Comparativo"):
                st.session_state.step = 5
                st.rerun()
        with col2:
            if st.button("➡️ Finalizar y Descargar Informe"):
                st.session_state.step = 7
                st.rerun()
        with col3:
            if st.button("🔄 Reiniciar App"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.session_state.step = 1
                st.rerun()

        if "nombre_localidad" not in st.session_state:
            cod_localidad = manzana_sel["num_localidad"].values[0]
            st.session_state.nombre_localidad = st.session_state.localidades.loc[
            st.session_state.localidades["num_localidad"] == cod_localidad, "nombre_localidad"
            ].values[0]

            # --- Bloque 7: Generación del Informe Ejecutivo ---

elif st.session_state.step == 7:
    st.subheader("📑 Generación del Informe Ejecutivo")

    # --- Generación del Mapa de Manzanas para el Informe ---
    import plotly.express as px
    import plotly.io as pio
    from io import BytesIO

    manzanas_localidad = st.session_state.manzanas_localidad_sel.copy()
    color_map = st.session_state.color_map

    if "uso_pot_simplificado" not in manzanas_localidad.columns:
        manzanas_localidad["uso_pot_simplificado"] = "Sin clasificación POT"

    bounds_m = manzanas_localidad.total_bounds
    center_m = {
        "lon": (bounds_m[0] + bounds_m[2]) / 2,
        "lat": (bounds_m[1] + bounds_m[3]) / 2
    }

    fig_manzanas = px.choropleth_mapbox(
        manzanas_localidad,
        geojson=manzanas_localidad.geometry,
        locations=manzanas_localidad.index,
        color="uso_pot_simplificado",
        color_discrete_map=color_map,
        mapbox_style="carto-positron",
        center=center_m,
        zoom=12,
        opacity=0.5,
        hover_name="id_manzana_unif"
    )

    fig_manzanas.update_layout(
        margin=dict(l=0, r=0, t=40, b=0),
        title="Manzanas seleccionadas para el informe"
    )
#OJO BUFFER MANZANAS
    buffer_manzanas = BytesIO()

    pio.write_image(fig_manzanas, buffer_manzanas, format='png', engine='kaleido')
    st.session_state.buffer_manzanas = buffer_manzanas
    #st.session_state.buffer_localidad = buffer_localidad
# Reemplazo de fig.write_image para compatibilidad con Streamlit Cloud
    #st.plotly_chart(fig_final, use_container_width=True)
    #st.session_state.buffer_manzanas = buffer_manzanas

    # --- Generación del Informe ---
    with st.spinner('📝 Generando informe...'):
        import base64

        manzana_id = st.session_state.manzana_sel
        manzana_sel = st.session_state.manzanas_localidad_sel[
            st.session_state.manzanas_localidad_sel["id_manzana_unif"] == manzana_id
        ]

        if manzana_sel.empty:
            st.error("❌ No se encontró la información de la manzana seleccionada. Por favor vuelve y selecciona.")
            if st.button("🔙 Volver al Análisis Comparativo"):
                st.session_state.step = 5
                st.rerun()
        else:
            estrato = int(manzana_sel["estrato"].values[0])
            id_manzana = manzana_sel["id_manzana_unif"].values[0]
            nombre_localidad = st.session_state.nombre_localidad
            colegios = int(manzana_sel["colegio_cerca"].values[0])
            estaciones = int(manzana_sel["estaciones_cerca"].values[0])

            texto0 = (
                f"El presente informe ha sido generado automáticamente como parte del trabajo final del Máster en Visual Analytics y Big Data "
                f"de la Universidad Internacional de La Rioja. Este documento es el resultado del proyecto desarrollado por "
                f"<strong>Sergio Andrés Fuentes Gómez</strong> y <strong>Miguel Alejandro González</strong>, bajo la dirección de "
                f"<strong>Mariana Ríos Ortegón</strong>. Forma parte de un piloto experimental orientado a la aplicación práctica de técnicas "
                f"de análisis visual y ciencia de datos en contextos urbanos reales."
            )


            texto1 = (
                f"De acuerdo con su selección, la manzana identificada con el código <strong>{id_manzana}</strong>, "
                f"ubicada en la localidad <strong>{nombre_localidad}</strong>, correspondiente al <strong>estrato {estrato}</strong>, "
                f"presenta condiciones clave para evaluar su potencial de valorización en el contexto urbano de Bogotá."
            )

            texto2 = (
                f"Cuenta con <strong>{colegios} colegios</strong> ubicados a menos de <strong>1.000 metros</strong> y "
                f"<strong>{estaciones} estaciones de TransMilenio</strong> a menos de <strong>500 metros</strong>. "
                f"Estos factores evidencian su buena conectividad y acceso a servicios."
            )

            id_area_manzana = manzana_sel["id_area"].values[0]
            area_info = st.session_state.areas[st.session_state.areas["id_area"] == id_area_manzana]
            area_pot = area_info["area_pot"].values[0]
            uso_pot = area_info["uso_pot_simplificado"].values[0]

            uso_pot_mayoritario = st.session_state.uso_pot_mayoritario
            valor_area = f"${st.session_state.promedio_area:,.0f}"

            texto3 = (
                f"Desde el punto de vista normativo, la manzana se encuentra asignada al área denominada "
                f"<strong>{area_pot}</strong> dentro del marco del <strong>Plan de Ordenamiento Territorial (POT)</strong>. "
                f"Su uso principal es <strong>{uso_pot}</strong>. En un radio de 500 metros, el uso predominante es "
                f"<strong>{uso_pot_mayoritario}</strong>. El valor promedio del metro cuadrado en el área POT es de "
                f"<strong>{valor_area}</strong>."
            )

            valor_m2 = manzana_sel["valor_m2"].values[0]
            rentabilidad = manzana_sel["rentabilidad"].values[0]
            promedio_buffer = float(st.session_state.promedio_buffer)

            texto4 = (
                f"El valor actual del metro cuadrado es de <strong>${valor_m2:,.0f}</strong>. "
                f"El promedio en un radio de 300 metros es de <strong>${promedio_buffer:,.0f}</strong>. "
                f"El valor promedio en el área POT es <strong>{valor_area}</strong>. La rentabilidad estimada es de "
                f"<strong>{rentabilidad}</strong>."
            )

            cod_loc = manzana_sel["num_localidad"].values[0]
            info_seguridad = st.session_state.df_seguridad[st.session_state.df_seguridad["num_localidad"] == cod_loc].iloc[0]
            nivel_riesgo = info_seguridad["nivel_riesgo_delictivo"]
            delitos = int(info_seguridad["cantidad_delitos"])

            texto5 = (
                f"La localidad <strong>{nombre_localidad}</strong> presenta un nivel de riesgo <strong>{nivel_riesgo}</strong> "
                f"con un total de <strong>{delitos} delitos</strong> reportados."
            )

            v_2025_1 = manzana_sel["valor_2025_s1"].values[0]
            v_2025_2 = manzana_sel["valor_2025_s2"].values[0]
            v_2026_1 = manzana_sel["valor_2026_s1"].values[0]
            v_2026_2 = manzana_sel["valor_2026_s2"].values[0]

            texto6 = (
                f"Según las proyecciones, el valor del metro cuadrado podría ser:<br>"
                f"- 2025-S1: <strong>${v_2025_1:,.0f}</strong><br>"
                f"- 2025-S2: <strong>${v_2025_2:,.0f}</strong><br>"
                f"- 2026-S1: <strong>${v_2026_1:,.0f}</strong><br>"
                f"- 2026-S2: <strong>${v_2026_2:,.0f}</strong><br>"
            )

            def buffer_a_base64(buffer):
                buffer.seek(0)
                return base64.b64encode(buffer.read()).decode('utf-8')

            img_colegios_base64 = buffer_a_base64(st.session_state.buffer_colegios)
            img_transporte_base64 = buffer_a_base64(st.session_state.buffer_transporte)
            img_distribucion_base64 = buffer_a_base64(st.session_state.buffer_dist_pot)
            img_mapapot_base64 = buffer_a_base64(st.session_state.buffer_mapa_pot)
            img_manzanas_base64 = buffer_a_base64(st.session_state.buffer_manzanas)
            img_valorm2_base64 = buffer_a_base64(st.session_state.buffer_valorm2)
            img_seguridad_base64 = buffer_a_base64(st.session_state.buffer_seguridad)
            img_proyeccion_base64 = buffer_a_base64(st.session_state.buffer_proyeccion)
            img_localidad_base64 = buffer_a_base64(st.session_state.buffer_localidad)

            html_ficha = st.session_state.ficha_estilizada.to_html()


            titulo = "Informe de Análisis de Inversión Inmobiliaria"

            html_content = f"""
            <!DOCTYPE html>
            <html lang="es">
            <head>
                <meta charset="UTF-8">
                <title>{titulo}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f9f9f9; }}
                    h1 {{ color: #2c3e50; text-align: center; }}
                    .container {{ display: flex; flex-direction: column; align-items: center; }}
                    .text {{ text-align: justify; margin: 20px 0; max-width: 900px; font-size: 16px; color: #333; }}
                    .images {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; max-width: 900px; margin: 0 auto; }}
                    .image {{ flex: 1; max-width: 600px; }}
                    .image img {{ width: 100%; height: auto; border: 1px solid #ccc; box-shadow: 2px 2px 8px rgba(0,0,0,0.1); }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>{titulo}</h1>
                    <div class="text">{html_ficha}</div>
                    <div class="text">{texto0}</div>
                    <div class="images"><div class="image"><img src="data:image/png;base64,{img_localidad_base64}"></div></div>
                    <div class="text">{texto1}</div>
                    <div class="images"><div class="image"><img src="data:image/png;base64,{img_manzanas_base64}"></div></div>
                    <div class="text">{texto2}</div>
                    <div class="images">
                        <div class="image"><img src="data:image/png;base64,{img_colegios_base64}"></div>
                        <div class="image"><img src="data:image/png;base64,{img_transporte_base64}"></div>
                    </div>
                    <div class="text">{texto3}</div>
                    <div class="images">

                        <div class="image"><img src="data:image/png;base64,{img_mapapot_base64}"></div>
                    </div>
                    <div class="text">{texto4}</div>
                    <div class="images"><div class="image"><img src="data:image/png;base64,{img_valorm2_base64}"></div></div>
                    <div class="text">{texto5}</div>
                    <div class="images"><div class="image"><img src="data:image/png;base64,{img_seguridad_base64}"></div></div>
                    <div class="text">{texto6}</div>
                    <div class="images"><div class="image"><img src="data:image/png;base64,{img_proyeccion_base64}"></div></div>
                </div>
            </body>
            </html>
            """

            st.session_state.informe_html = html_content

    st.success("✅ Informe generado correctamente.")

    st.download_button(
        "📥 Descargar Informe (HTML)",
        data=st.session_state.informe_html,
        file_name="Informe_Valorizacion.html",
        mime="text/html"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔙 Volver al Análisis de Seguridad"):
            st.session_state.step = 6
            st.rerun()
    with col2:
        if st.button("🔄 Reiniciar Aplicación"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.step = 1
            st.rerun()
