[CmdletBinding()]
param(
    [string]$OutputDirectory = (
        Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'fuentes_descargadas'
    )
)

$ErrorActionPreference = 'Stop'
$captureDate = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'
$userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) RegulabankSourceCollector/1.0'

$sources = @(
    [pscustomobject]@{ Id=1; Section='01_normativa_peruana'; Title='Ley General del Sistema Financiero - Ley 26702'; OriginalUrl='https://www.sbs.gob.pe/ley-general-del-sistema-financiero'; ValidatedUrl='https://www.sbs.gob.pe/Portals/0/Ley%20N%2026702%20(Mod%20DL%201646)%20(1).pdf'; DownloadUrl='https://leyes.congreso.gob.pe/Documentos/Leyes/26702.pdf'; FileName='01_ley_26702_texto_original.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente con modificaciones'; Note='El enlace del DOCX no resuelve. La SBS publica un texto concordado actualizado al 01-06-2025, pero bloquea la descarga automatizada; se conserva el texto original oficial del Congreso.' },
    [pscustomobject]@{ Id=2; Section='01_normativa_peruana'; Title='Decreto Legislativo 1531 - adecuacion a Basilea III'; OriginalUrl='https://busquedas.elperuano.pe/normaslegales/decreto-legislativo-que-modifica-la-ley-general-del-sistema-fin-decreto-legislativo-n-1531-2005943-1/'; ValidatedUrl='https://www.leyes.congreso.gob.pe/Documentos/2021_2026/Boletin_de_Normas_Legales/2022/NL20220319.pdf'; DownloadUrl='https://www.leyes.congreso.gob.pe/Documentos/2021_2026/Boletin_de_Normas_Legales/2022/NL20220319.pdf'; FileName='02_dl_1531_boletin_normas_2022-03-19.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente con modificaciones'; Note='La ruta de El Peruano del DOCX es obsoleta o inconsistente. Se descarga el boletin oficial del Congreso que contiene el DL 1531.' },
    [pscustomobject]@{ Id=3; Section='01_normativa_peruana'; Title='Resolucion SBS 9075-2012 - liquidez'; OriginalUrl='https://www.sbs.gob.pe/normativa/resolucion-9075-2012'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/671/v6.0/Adjuntos/9075-2012.r.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/671/v6.0/Adjuntos/9075-2012.r.pdf'; FileName='03_res_sbs_9075-2012_historica.pdf'; Kind='pdf'; Validation='DESACTUALIZADA'; Validity='Derogada desde 2024-01-01'; Note='La Resolucion SBS 4221-2023 derogo el reglamento aprobado por la Resolucion SBS 9075-2012. Se descarga como antecedente historico.' },
    [pscustomobject]@{ Id=4; Section='01_normativa_peruana'; Title='Resolucion SBS 3296-2022 - actualizacion RCL'; OriginalUrl='https://www.sbs.gob.pe/normativa/resolucion-3296-2022'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/2210/v1.0/Adjuntos/3296-2022.R.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/2210/v1.0/Adjuntos/3296-2022.R.pdf'; FileName='04_res_sbs_3296-2022_historica.pdf'; Kind='pdf'; Validation='DESACTUALIZADA'; Validity='Antecedente de norma derogada'; Note='Modifico la Resolucion SBS 9075-2012, posteriormente derogada por la Resolucion SBS 4221-2023.' },
    [pscustomobject]@{ Id=5; Section='01_normativa_peruana'; Title='Resolucion SBS 4221-2023 - nuevo reglamento de liquidez y RFNE'; OriginalUrl='https://www.sbs.gob.pe/normativa/resolucion-4221-2023'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/2322/v1.0/Adjuntos/4221-2023.r.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/2322/v1.0/Adjuntos/4221-2023.r.pdf'; FileName='05_res_sbs_4221-2023_liquidez_rfne.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente'; Note='Norma vigente que reemplaza el reglamento aprobado por la Resolucion SBS 9075-2012.' },
    [pscustomobject]@{ Id=6; Section='01_normativa_peruana'; Title='Reglamento de clasificacion y provisiones - Resolucion SBS 11356-2008'; OriginalUrl='https://www.sbs.gob.pe/normativa/reglamento-de-clasificacion-y-provisiones'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1097/v12.0/Adjuntos/11356-2008.r.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1097/v12.0/Adjuntos/11356-2008.r.pdf'; FileName='06_res_sbs_11356-2008_clasificacion_provisiones_v12.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente y modificada'; Note='Se descarga la version consolidada v12 de la fuente oficial SBS.' },
    [pscustomobject]@{ Id=7; Section='01_normativa_peruana'; Title='Riesgo de mercado - Resolucion SBS 6328-2009'; OriginalUrl='https://www.sbs.gob.pe/normativa/riesgo-de-mercado'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/715/v4.0/Adjuntos/6328-2009.r.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/715/v4.0/Adjuntos/6328-2009.r.pdf'; FileName='07_res_sbs_6328-2009_riesgo_mercado_v4.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente'; Note='La ruta generica del DOCX se reemplaza por el PDF oficial vigente.' },
    [pscustomobject]@{ Id=8; Section='01_normativa_peruana'; Title='Riesgo operacional - Resolucion SBS 2116-2009'; OriginalUrl='https://www.sbs.gob.pe/normativa/riesgo-operacional'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/842/v4.0/Adjuntos/2116-2009%20actualizado%20con%20la%20877-2020.doc.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/842/v4.0/Adjuntos/2116-2009%20actualizado%20con%20la%20877-2020.doc.pdf'; FileName='08_res_sbs_2116-2009_riesgo_operacional_v4.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente y modificada'; Note='Version oficial actualizada con la Resolucion SBS 877-2020.' },
    [pscustomobject]@{ Id=9; Section='01_normativa_peruana'; Title='Gestion de riesgos LAFT - Resolucion SBS 2660-2015'; OriginalUrl='https://www.sbs.gob.pe/normativa/lavado-de-activos'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1540/v5.0/Adjuntos/2660-2015.r.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1540/v5.0/Adjuntos/2660-2015.r.pdf'; FileName='09_res_sbs_2660-2015_gestion_riesgos_laft_v5.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente y modificada'; Note='Se descarga la version consolidada v5 de la fuente oficial SBS.' },
    [pscustomobject]@{ Id=10; Section='01_normativa_peruana'; Title='Ley 29733 - Proteccion de Datos Personales'; OriginalUrl='https://www.minjus.gob.pe/ley-de-proteccion-de-datos-personales/'; ValidatedUrl='https://www.leyes.congreso.gob.pe/documentos/leyes/29733.pdf'; DownloadUrl='https://www.leyes.congreso.gob.pe/documentos/leyes/29733.pdf'; FileName='10_ley_29733_proteccion_datos.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente con modificaciones'; Note='El enlace antiguo de MINJUSDH se reemplaza por el PDF oficial del Congreso.' },
    [pscustomobject]@{ Id=11; Section='01_normativa_peruana'; Title='Reglamento de la Ley 29733 - Decreto Supremo 016-2024-JUS'; OriginalUrl='https://www.minjus.gob.pe/reglamento-de-la-ley-de-proteccion-de-datos-personales/'; ValidatedUrl='https://cdn.www.gob.pe/uploads/document/file/7568330/6426760-decreto-supremo-n-016-2024-jus-reglamento-de-la-ley-n-29733-ley-de-proteccion-de-datos-personales-publicado-nov-2024.pdf'; DownloadUrl='https://cdn.www.gob.pe/uploads/document/file/7568330/6426760-decreto-supremo-n-016-2024-jus-reglamento-de-la-ley-n-29733-ley-de-proteccion-de-datos-personales-publicado-nov-2024.pdf'; FileName='11_ds_016-2024-jus_reglamento_ley_29733.pdf'; Kind='pdf'; Validation='REEMPLAZADA'; Validity='Vigente desde 2025-03-31'; Note='El DS 016-2024-JUS aprobo el nuevo Reglamento y sustituyo al DS 003-2013-JUS.' },
    [pscustomobject]@{ Id=12; Section='01_normativa_peruana'; Title='Seguridad de la informacion y ciberseguridad - Resolucion SBS 504-2021'; OriginalUrl='https://www.sbs.gob.pe/normativa/seguridad-de-la-informacion'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/2046/v5.0/Adjuntos/504-2021.R.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/2046/v5.0/Adjuntos/504-2021.R.pdf'; FileName='12_res_sbs_504-2021_seguridad_informacion_v5.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente y modificada'; Note='Se descarga la version oficial consolidada disponible.' },
    [pscustomobject]@{ Id=13; Section='01_normativa_peruana'; Title='Tercerizacion - Resolucion SBS 272-2017'; OriginalUrl='https://www.sbs.gob.pe/normativa/tercerizacion'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1708/v7.0/Adjuntos/272-2017.R.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1708/v7.0/Adjuntos/272-2017.R.pdf'; FileName='13_res_sbs_272-2017_gobierno_riesgos_tercerizacion_v7.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente y modificada en 2026'; Note='La tercerizacion esta regulada dentro del Reglamento de Gobierno Corporativo y Gestion Integral de Riesgos. Se descarga la version v7.' },
    [pscustomobject]@{ Id=14; Section='01_normativa_peruana'; Title='Sistemas de pagos y liquidacion de valores - Ley 29440'; OriginalUrl='https://www.bcrp.gob.pe/sistemas-de-pago.html'; ValidatedUrl='https://www.bcrp.gob.pe/docs/sistema-de-pagos/ley-29440.pdf'; DownloadUrl='https://www.leyes.congreso.gob.pe/Documentos/Leyes/29440.pdf'; FileName='14_ley_29440_sistemas_pagos_liquidacion.pdf'; Kind='pdf'; Validation='VALIDA_CON_ALTERNATIVA'; Validity='Vigente'; Note='El portal BCRP es valido pero bloquea descargas automatizadas. Se descarga la misma ley desde el Congreso.' },
    [pscustomobject]@{ Id=15; Section='01_normativa_peruana'; Title='Tarjetas de credito y debito - Resolucion SBS 6523-2013'; OriginalUrl='https://www.sbs.gob.pe/normativa/medios-de-pago'; ValidatedUrl='https://intranet2.sbs.gob.pe/dv_int_cn/718/v11.0/Adjuntos/6523-2013.R%20.pdf'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/718/v11.0/Adjuntos/6523-2013.R%20.pdf'; FileName='15_res_sbs_6523-2013_tarjetas_v11.pdf'; Kind='pdf'; Validation='CORREGIDA'; Validity='Vigente y modificada'; Note='La referencia generica se concreta en el Reglamento de Tarjetas de Credito y Debito, version v11.' },
    [pscustomobject]@{ Id=16; Section='01_normativa_peruana'; Title='UIF - reportes ROS y operaciones sospechosas'; OriginalUrl='https://www.uif.gob.pe/'; ValidatedUrl='https://www.sbs.gob.pe/prevencion-de-lavado-activos/supervisados/plaft-portal-de-prevencion-de-lavado-de-activos-y-financiamiento-del-terrorismo'; DownloadUrl='https://intranet2.sbs.gob.pe/dv_int_cn/1766/v1.0/Adjuntos/789-2018.R.pdf'; FileName='16_res_sbs_789-2018_plaft_ros.pdf'; Kind='pdf'; Validation='REUBICADA'; Validity='Portal UIF integrado en SBS'; Note='El dominio uif.gob.pe ya no es la fuente operativa. Se valida el Portal PLAFT de SBS y se descarga la norma oficial aplicable a reportes y PLAFT.' },
    [pscustomobject]@{ Id=17; Section='01_normativa_peruana'; Title='Manuales y guias UIF'; OriginalUrl='https://www.uif.gob.pe/guias'; ValidatedUrl='https://www.sbs.gob.pe/prevencion-de-lavado-activos/mapa-de-sitio'; DownloadUrl=''; FileName='17_guias_uif_sbs.url'; Kind='url'; Validation='REUBICADA'; Validity='Coleccion dinamica vigente'; Note='Las guias se trasladaron al Portal de Prevencion de Lavado de Activos de la SBS. Se crea un acceso directo porque es una coleccion dinamica, no un unico documento.' },

    [pscustomobject]@{ Id=18; Section='02_normativa_internacional'; Title='Basel III - Basel Framework consolidado'; OriginalUrl='https://www.bis.org/bcbs/basel3.htm'; ValidatedUrl='https://www.bis.org/basel_framework/'; DownloadUrl='https://www.bis.org/committees/bcbs/basel-framework/basel-framework.pdf'; FileName='18_bis_basel_framework_2026.pdf'; Kind='pdf'; Validation='ACTUALIZADA'; Validity='Marco consolidado vigente desde 2026-01-01'; Note='La pagina historica Basel III se sustituye por el Basel Framework consolidado vigente.' },
    [pscustomobject]@{ Id=19; Section='02_normativa_internacional'; Title='Principios de riesgo operacional BCBS'; OriginalUrl='https://www.bis.org/publ/bcbs195.htm'; ValidatedUrl='https://www.bis.org/bcbs/publ/d515.htm'; DownloadUrl='https://www.bis.org/publications/202103-guidelines-revisions-principles-sound-management-operational-risk.pdf'; FileName='19_bcbs_principios_riesgo_operacional_2021.pdf'; Kind='pdf'; Validation='REEMPLAZADA'; Validity='Version revisada vigente de 2021'; Note='BCBS 195 (2011) fue sustituido por los Principios revisados de 2021 (BCBS d515).' },
    [pscustomobject]@{ Id=20; Section='02_normativa_internacional'; Title='Recomendaciones GAFI FATF'; OriginalUrl='https://www.fatf-gafi.org/recommendations.html'; ValidatedUrl='https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Fatf-recommendations.html'; DownloadUrl='https://biblioteca.gafilat.org/wp-content/uploads/2026/01/Recomendaciones-y-Metodologia-Diciembre-2025.pdf'; FileName='20_gafilat_recomendaciones_y_metodologia_dic_2025.pdf'; Kind='pdf'; Validation='ACTUALIZADA_CON_COPIA_REGIONAL'; Validity='FATF actualizado en junio de 2026'; Note='FATF bloquea la descarga automatizada. Se descarga la copia oficial regional GAFILAT en espanol de diciembre de 2025; la pagina validada FATF indica una revision posterior en junio de 2026.' },
    [pscustomobject]@{ Id=21; Section='02_normativa_internacional'; Title='ISO IEC 27001'; OriginalUrl='https://www.iso.org/isoiec-27001-information-security.html'; ValidatedUrl='https://www.iso.org/standard/27001'; DownloadUrl=''; FileName='21_iso_iec_27001-2022.url'; Kind='url'; Validation='ACTUALIZADA_ACCESO_COMERCIAL'; Validity='ISO IEC 27001:2022 con Amd 1:2024'; Note='La edicion vigente es ISO/IEC 27001:2022 con enmienda 1:2024. El texto completo es comercial; no se copia sin licencia. Se crea un acceso directo oficial.' },
    [pscustomobject]@{ Id=22; Section='02_normativa_internacional'; Title='ISO 22301'; OriginalUrl='https://www.iso.org/standard/50038.html'; ValidatedUrl='https://www.iso.org/standard/75106.html'; DownloadUrl=''; FileName='22_iso_22301-2019.url'; Kind='url'; Validation='REEMPLAZADA_ACCESO_COMERCIAL'; Validity='ISO 22301:2019 con Amd 1:2024'; Note='La edicion 2012 (ID 50038) fue retirada. La vigente es ISO 22301:2019 con enmienda 1:2024; el texto completo es comercial.' },
    [pscustomobject]@{ Id=23; Section='02_normativa_internacional'; Title='Reglamento de Inteligencia Artificial de la Union Europea'; OriginalUrl='https://artificialintelligenceact.eu/'; ValidatedUrl='https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:02024R1689-20260727'; DownloadUrl='https://op.europa.eu/o/opportal-service/download-handler?identifier=b1730fb2-8f1c-11f1-9262-01aa75ed71a1&format=PDF&language=es&productionSystem=cellar'; FileName='23_ue_ai_act_texto_consolidado_2026-07-27_es.pdf'; Kind='pdf'; Validation='REEMPLAZADA_POR_FUENTE_OFICIAL'; Validity='En vigor, texto consolidado 2026-07-27'; Note='El sitio del DOCX no es la fuente oficial. Se descarga desde la Oficina de Publicaciones de la UE el texto EUR-Lex consolidado en espanol, posterior a la modificacion de 2026.' },

    [pscustomobject]@{ Id=24; Section='03_noticias_publicaciones'; Title='Noticias SBS'; OriginalUrl='https://www.sbs.gob.pe/noticias'; ValidatedUrl='https://www.gob.pe/institucion/sbs/noticias'; DownloadUrl='https://www.gob.pe/institucion/sbs/noticias'; FileName='24_noticias_sbs_2026-10-17.html'; Kind='html'; Validation='REUBICADA'; Validity='Indice dinamico vigente'; Note='Se guarda una captura HTML del indice oficial en gob.pe.' },
    [pscustomobject]@{ Id=25; Section='03_noticias_publicaciones'; Title='Comunicados BCRP'; OriginalUrl='https://www.bcrp.gob.pe/comunicados.html'; ValidatedUrl='https://www.bcrp.gob.pe/comunicados.html'; DownloadUrl=''; FileName='25_comunicados_bcrp.url'; Kind='url'; Validation='VALIDA_BLOQUEO_AUTOMATIZADO'; Validity='Indice dinamico vigente'; Note='La pagina es valida, pero el sitio devuelve un bloqueo Incapsula a descargas automatizadas. Se crea un acceso directo y se registra el impedimento.' },
    [pscustomobject]@{ Id=26; Section='03_noticias_publicaciones'; Title='Noticias UIF Peru'; OriginalUrl='https://www.uif.gob.pe/noticias'; ValidatedUrl='https://www.gob.pe/institucion/sbs/noticias?term=UIF'; DownloadUrl='https://www.gob.pe/institucion/sbs/noticias?term=UIF'; FileName='26_noticias_uif_sbs_2026-10-17.html'; Kind='html'; Validation='REUBICADA'; Validity='Indice dinamico vigente'; Note='UIF-Peru esta integrada en la SBS. Se guarda una captura HTML de noticias SBS filtrada por UIF.' },
    [pscustomobject]@{ Id=27; Section='03_noticias_publicaciones'; Title='Comunicados de prensa BIS'; OriginalUrl='https://www.bis.org/press/index.htm'; ValidatedUrl='https://www.bis.org/media/news'; DownloadUrl='https://www.bis.org/media/news'; FileName='27_bis_media_releases_2026-10-17.html'; Kind='html'; Validation='REUBICADA'; Validity='Indice dinamico vigente'; Note='La ruta press/index.htm ya no existe; se reemplaza por el indice actual Media releases.' },
    [pscustomobject]@{ Id=28; Section='03_noticias_publicaciones'; Title='Publicaciones FATF GAFI'; OriginalUrl='https://www.fatf-gafi.org/publications/'; ValidatedUrl='https://www.fatf-gafi.org/en/publications.html'; DownloadUrl='https://biblioteca.gafilat.org/'; FileName='28_biblioteca_gafilat_2026-10-17.html'; Kind='html'; Validation='REUBICADA_CON_COPIA_REGIONAL'; Validity='Indice dinamico vigente'; Note='La ruta FATF cambio y el sitio bloquea la captura automatizada. Se guarda como respaldo el indice de la biblioteca oficial regional GAFILAT.' }
)

function Test-DownloadedFile {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Kind
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -eq 0) { return $false }

    if ($Kind -eq 'pdf') {
        if ($item.Length -lt 1024) { return $false }
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        if ($bytes.Length -lt 4) { return $false }
        return ([System.Text.Encoding]::ASCII.GetString($bytes, 0, 4) -eq '%PDF')
    }

    if ($Kind -eq 'html') {
        if ($item.Length -lt 10000) { return $false }
        $reader = [System.IO.StreamReader]::new($Path, $true)
        try {
            $buffer = New-Object char[] 8192
            $read = $reader.ReadBlock($buffer, 0, $buffer.Length)
            $sample = -join $buffer[0..([Math]::Max(0, $read - 1))]
        } finally {
            $reader.Dispose()
        }
        return ($sample -notmatch 'Request unsuccessful|Incapsula|Access Denied|Just a moment|Forbidden')
    }

    return $true
}

function Write-InternetShortcut {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Url
    )
    $content = "[InternetShortcut]`r`nURL=$Url`r`n"
    [System.IO.File]::WriteAllText($Path, $content, [System.Text.UTF8Encoding]::new($false))
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
foreach ($section in ($sources.Section | Sort-Object -Unique)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $OutputDirectory $section) | Out-Null
}

$results = New-Object System.Collections.Generic.List[object]

foreach ($source in $sources) {
    $sectionDirectory = Join-Path $OutputDirectory $source.Section
    $destination = Join-Path $sectionDirectory $source.FileName
    $downloadStatus = 'PENDIENTE'
    $httpStatus = ''
    $contentType = ''
    $errorMessage = ''

    if ($source.Kind -eq 'url') {
        Write-InternetShortcut -Path $destination -Url $source.ValidatedUrl
        $downloadStatus = 'ACCESO_DIRECTO_CREADO'
    } else {
        if (Test-DownloadedFile -Path $destination -Kind $source.Kind) {
            $downloadStatus = 'DESCARGADO_Y_VALIDADO'
            $httpStatus = 'LOCAL'
            $contentType = if ($source.Kind -eq 'pdf') { 'application/pdf' } else { 'text/html' }
        } else {
            $partPath = "$destination.part"
            if (Test-Path -LiteralPath $partPath) { Remove-Item -LiteralPath $partPath -Force }

            $curlOutput = & curl.exe -L --fail --silent --show-error --retry 2 --connect-timeout 20 --max-time 300 `
                -A $userAgent -o $partPath -w '%{http_code}|%{content_type}' $source.DownloadUrl 2>&1
            $curlExitCode = $LASTEXITCODE
            $downloadHost = ([System.Uri]$source.DownloadUrl).Host
            if ($downloadHost -match '(sbs\.gob\.pe|congreso\.gob\.pe|www\.gob\.pe)$') {
                Start-Sleep -Seconds 5
            }
            $curlText = ($curlOutput | ForEach-Object { $_.ToString() }) -join "`n"
            if ($curlText -match '(?m)(\d{3})\|([^\r\n]*)$') {
                $httpStatus = $Matches[1]
                $contentType = $Matches[2]
            }

            if ($curlExitCode -eq 0 -and (Test-DownloadedFile -Path $partPath -Kind $source.Kind)) {
                Move-Item -LiteralPath $partPath -Destination $destination -Force
                $downloadStatus = 'DESCARGADO_Y_VALIDADO'
                $oldFailurePath = [System.IO.Path]::ChangeExtension($destination, '.NO_DESCARGADO.txt')
                if (Test-Path -LiteralPath $oldFailurePath) { Remove-Item -LiteralPath $oldFailurePath -Force }
            } else {
                if (Test-Path -LiteralPath $partPath) { Remove-Item -LiteralPath $partPath -Force }
                $downloadStatus = 'FALLO_DESCARGA'
                $errorMessage = "curl=$curlExitCode; $curlText"
                $failurePath = [System.IO.Path]::ChangeExtension($destination, '.NO_DESCARGADO.txt')
                $failureText = @"
Titulo: $($source.Title)
URL validada: $($source.ValidatedUrl)
URL intentada: $($source.DownloadUrl)
Resultado: $downloadStatus
Detalle: $errorMessage
Observacion: $($source.Note)
"@
                [System.IO.File]::WriteAllText($failurePath, $failureText, [System.Text.UTF8Encoding]::new($false))
                $destination = $failurePath
            }
        }
    }

    $file = Get-Item -LiteralPath $destination
    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    $outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
    $absoluteDestination = [System.IO.Path]::GetFullPath($destination)
    $relativePath = $absoluteDestination.Substring($outputRoot.Length).TrimStart([System.IO.Path]::DirectorySeparatorChar)

    $results.Add([pscustomobject]@{
        id = $source.Id
        seccion = $source.Section
        titulo = $source.Title
        url_original = $source.OriginalUrl
        estado_validacion = $source.Validation
        vigencia = $source.Validity
        url_validada = $source.ValidatedUrl
        url_descarga = $source.DownloadUrl
        resultado_descarga = $downloadStatus
        http_status = $httpStatus
        content_type = $contentType
        archivo = $relativePath
        tamano_bytes = $file.Length
        sha256 = $hash
        fecha_captura = $captureDate
        observacion = $source.Note
        error = $errorMessage
    })

    Write-Host ("[{0:00}/28] {1}: {2}" -f $source.Id, $downloadStatus, $source.Title)
}

$csvPath = Join-Path $OutputDirectory 'validacion_fuentes.csv'
$jsonPath = Join-Path $OutputDirectory 'manifest.json'
$readmePath = Join-Path $OutputDirectory 'README.md'

$results | Sort-Object id | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
$results | Sort-Object id | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$downloadedCount = @($results | Where-Object resultado_descarga -eq 'DESCARGADO_Y_VALIDADO').Count
$shortcutCount = @($results | Where-Object resultado_descarga -eq 'ACCESO_DIRECTO_CREADO').Count
$failedCount = @($results | Where-Object resultado_descarga -eq 'FALLO_DESCARGA').Count
$outdatedCount = @($results | Where-Object { $_.estado_validacion -match 'DESACTUALIZADA|REEMPLAZADA' }).Count

$readme = @"
# Fuentes verificadas y descargadas

Fecha de captura: $captureDate
Archivo de origen: `docs/brief/sources.docx`
Total de fuentes: $($results.Count)

## Resultado

- Documentos o capturas descargados y validados: $downloadedCount
- Accesos directos creados para colecciones dinamicas o contenido comercial: $shortcutCount
- Descargas fallidas con registro de error: $failedCount
- Referencias marcadas como desactualizadas o reemplazadas: $outdatedCount

Cada archivo descargado fue comprobado por firma PDF o por contenido HTML minimo. El inventario validacion_fuentes.csv y el manifiesto manifest.json incluyen URL original, URL validada, vigencia, estado de descarga, fecha, tamano y SHA-256.

## Hallazgos principales

- La Resolucion SBS 9075-2012 fue derogada por la Resolucion SBS 4221-2023 desde el 1 de enero de 2024.
- El Reglamento de la Ley 29733 aprobado por DS 003-2013-JUS fue sustituido por el DS 016-2024-JUS, vigente desde el 31 de marzo de 2025.
- BCBS 195 (2011) fue sustituido por los principios revisados de riesgo operacional publicados en 2021.
- ISO 22301:2012 fue retirada; la edicion vigente es ISO 22301:2019 con la enmienda 1:2024.
- Para el Reglamento de IA de la UE se usa EUR-Lex, no el sitio privado indicado en el DOCX.
- El antiguo dominio de la UIF-Peru fue reemplazado por el portal especializado de la SBS.

## Nota de uso

La validacion es una fotografia al momento de la captura. Antes de usar una norma para una decision legal o de cumplimiento, revisar nuevamente su historial oficial de modificaciones y su fecha de entrada en vigor.
"@
[System.IO.File]::WriteAllText($readmePath, $readme, [System.Text.UTF8Encoding]::new($false))

Write-Host ''
Write-Host "Inventario: $csvPath"
Write-Host "Manifiesto: $jsonPath"
Write-Host "Resumen: $readmePath"
Write-Host "Descargados=$downloadedCount; AccesosDirectos=$shortcutCount; Fallidos=$failedCount"
