include("${CMAKE_CURRENT_LIST_DIR}/../../cmake/KPXCDeployQt.cmake")

if(TEST_CASE STREQUAL "windows-x64-to-arm64")
    kpxc_resolve_vcpkg_deployqt(
            HOST_SYSTEM_NAME Windows
            HOST_SYSTEM_PROCESSOR AMD64
            VCPKG_INSTALLED_DIR C:/vcpkg_installed
            VCPKG_TARGET_TRIPLET arm64-windows-release
            TARGET_QT_PREFIX C:/vcpkg_installed/arm64-windows-release
            DEPLOYQT_EXE_NAME windeployqt.exe
            OUT_EXECUTABLE executable
            OUT_ARGUMENTS arguments
            OUT_HOST_TRIPLET host_triplet)
    if(NOT host_triplet STREQUAL "x64-windows")
        message(FATAL_ERROR "Expected x64-windows host triplet, found ${host_triplet}")
    endif()
    if(NOT executable STREQUAL
            "C:/vcpkg_installed/x64-windows/tools/Qt6/bin/windeployqt.exe")
        message(FATAL_ERROR "Unexpected host deployment tool: ${executable}")
    endif()
    if(NOT arguments STREQUAL
            "--qtpaths;C:/vcpkg_installed/arm64-windows-release/tools/Qt6/bin/qtpaths.bat")
        message(FATAL_ERROR "Unexpected target deployment arguments: ${arguments}")
    endif()
elseif(TEST_CASE STREQUAL "macos-x64-to-arm64")
    kpxc_resolve_vcpkg_deployqt(
            HOST_SYSTEM_NAME Darwin
            HOST_SYSTEM_PROCESSOR x86_64
            VCPKG_INSTALLED_DIR /vcpkg_installed
            VCPKG_TARGET_TRIPLET arm64-osx
            TARGET_QT_PREFIX /vcpkg_installed/arm64-osx
            DEPLOYQT_EXE_NAME macdeployqt
            OUT_EXECUTABLE executable
            OUT_ARGUMENTS arguments
            OUT_HOST_TRIPLET host_triplet)
    if(NOT host_triplet STREQUAL "x64-osx")
        message(FATAL_ERROR "Expected x64-osx host triplet, found ${host_triplet}")
    endif()
    if(NOT executable STREQUAL
            "/vcpkg_installed/x64-osx/tools/Qt6/bin/macdeployqt")
        message(FATAL_ERROR "Unexpected host deployment tool: ${executable}")
    endif()
    if(NOT arguments STREQUAL "-libpath=/vcpkg_installed/arm64-osx/lib")
        message(FATAL_ERROR "Unexpected target deployment arguments: ${arguments}")
    endif()
else()
    message(FATAL_ERROR "Unknown TEST_CASE: ${TEST_CASE}")
endif()
